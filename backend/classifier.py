"""
Call classification engine — ported as-is from the battle-tested classifier.py.
Entry point: classify(row) -> (outcome, sub_category)
"""
import pandas as pd
import re


def parse_transcript(raw):
    if pd.isna(raw) or not raw.strip():
        return "", "", 0, 0, []
    user_parts = []
    agent_parts = []
    turns = []
    pattern = r'\{"(agent|user)"\s*:\s*"((?:[^"\\]|\\.)*)"\}'
    for m in re.finditer(pattern, raw):
        role, text = m.group(1), m.group(2)
        text = text.replace('\\"', '"').replace('\\n', ' ').strip()
        if text:
            turns.append((role, text))
            if role == "user":
                user_parts.append(text)
            else:
                agent_parts.append(text)
    user_text = " ".join(user_parts)
    agent_text = " ".join(agent_parts)
    user_words = len(user_text.split()) if user_text.strip() else 0
    return user_text, agent_text, user_words, len(user_parts), turns


def has_phrase(text, phrases):
    t = text.lower()
    for p in phrases:
        if p.lower() in t:
            return True
    return False


def count_number_words(text):
    number_words = ["zero","one","two","three","four","five","six","seven","eight","nine"]
    return sum(1 for w in text.lower().split() if w in number_words)


def count_inaudible(text):
    return text.lower().count("inaudible")


VM_ENGLISH = ["voice mail","voicemail","leave your message","leave a message","not available","after the tone","record your message","at the beep","after the beep","mailbox","is not in service","has been disconnected","forwarded to voice","been forwarded","the person you","please leave your","press one","press two","press pound","replay your message","continue recording","delivery options","this mailbox is full","subscriber","for a faster response","do not leave a voice","cannot accept new messages","currently full"]
VM_SPANISH = ["deje su mensaje","buzón de voz","no está disponible","graba tu mensaje","puedes colgar"]
VM_SCREENING = ["reason for calling","motivo de tu llamada","esta persona está disponible","please stay on the line","permanece en la línea"]
VM_PERSONAL = ["leave your name and number","leave your name and phone","i was not able to answer","sorry i missed your call","return your call as soon","i will get back","i'm not in at the moment","i missed your call","leave me a message"]
REAL_CONVO = ["hello?","yes.","speaking","who is this"]


def classify(row):
    appt_booked = str(row.get("Appointment Booked","")).strip().lower()
    in_vm = str(row.get("In Voicemail","")).strip().upper()
    transcript = str(row.get("Transcript",""))

    user_text, agent_text, user_words, user_turns, turns = parse_transcript(transcript)
    ut = user_text.lower()
    at = agent_text.lower()

    # P1: Accepted appointment — system flag
    if appt_booked == "yes":
        return "Accepted appointment", "Booked via system flag"

    # P1b: Accepted appointment — scheduling language
    confirm_phrases = ["scheduled","booked","we'll see you","you're all set","confirmed for","your appointment","see you on"]
    patient_confirms = ["yes","okay","ok","sure","sounds good","that works","perfect","great","alright"]
    if has_phrase(at, confirm_phrases) and has_phrase(ut, patient_confirms):
        return "Accepted appointment", "Scheduling language confirmed"

    # P1c: Spanish appointment confirmations
    spanish_confirms = ["sí","si,","ok","okay","gracias","bueno","está bien","ya"]
    agent_appt_phrases = ["confirmar","cita","appointment","podrá asistir","asistir a esta","su cita","tarjeta de seguro","identificación con foto"]
    if has_phrase(at, agent_appt_phrases) and has_phrase(ut, spanish_confirms) and user_words <= 15:
        no_count = ut.count(" no ") + ut.count("no,") + (1 if ut.startswith("no") else 0)
        si_count = ut.count("sí") + ut.count("si,") + ut.count("si.") + ut.count("ok")
        if si_count > no_count:
            return "Accepted appointment", "Scheduling language confirmed"

    # P1d: Third party confirming appointment
    third_party_confirm = ["this is his father","this is her mother","this is his mother","this is her father","her daughter","his son","her son"]
    if has_phrase(ut, third_party_confirm) and has_phrase(at, ["confirm","appointment","cita","will be able"]):
        if has_phrase(ut, ["yes","we'll be there","she'll be there","he'll be there","will be there"]):
            return "Accepted appointment", "Third party confirmed appointment"

    # P2: VM flag
    if in_vm == "TRUE":
        pass_to_vm_flag = True
    else:
        pass_to_vm_flag = False

    # P3: VM transcript-based
    def check_vm_transcript():
        if user_words >= 80:
            return None, None
        if has_phrase(ut, REAL_CONVO) and user_words > 30:
            return None, None
        if has_phrase(ut, VM_SPANISH):
            return "Voicemail left", "VM system (Spanish)"
        if has_phrase(ut, VM_SCREENING):
            return "Voicemail left", "Automated call screening"
        if has_phrase(ut, VM_PERSONAL):
            return "Voicemail left", "Personal answering machine"
        if count_number_words(ut) >= 5 and user_words < 20:
            return "Voicemail left", "VM number recitation"
        if has_phrase(ut, VM_ENGLISH):
            return "Voicemail left", "VM system detected in transcript"
        return None, None

    if pass_to_vm_flag:
        vm_out, vm_sub = check_vm_transcript()
        if vm_out:
            return vm_out, vm_sub
        return "Voicemail left", "VM flag detected"

    vm_out, vm_sub = check_vm_transcript()
    if vm_out:
        return vm_out, vm_sub

    # P4: Wrong number / Deceased / Relocated
    if has_phrase(ut, ["passed away","deceased","he died","she died"]):
        return "Other - Wrong number/Deceased", "Patient deceased"
    if has_phrase(ut, ["not living in new york","i moved","he's in his country","no longer","moved away"]):
        return "Other - Patient relocated", "Patient moved/relocated"
    if has_phrase(ut, ["wrong number","wrong person","doesn't live here","no one by that name"]):
        return "Other - Wrong number/Deceased", "Wrong number/person"

    # P5: Third party answered
    third_party_phrases = ["this is not","she's not here","he's not here","not here right now","ella no se encuentra","he's at work"]
    if has_phrase(ut, third_party_phrases) and user_words < 40:
        if has_phrase(ut, ["another time","tomorrow","call back"]):
            return "Requested callback", "Third party - patient unavailable"
        return "Other - Third party answered", "Non-patient answered"

    # P5b: Third party with callback scheduling
    third_party_markers = ["his father","her mother","his mother","her father","her daughter","his son","her son","with her son","this is walter"]
    if has_phrase(ut, third_party_markers) and user_words < 40:
        if has_phrase(ut, ["tomorrow","call back","better time","wednesday","thursday","monday","tuesday","friday"]) or has_phrase(at, ["call back","i'll call"]):
            return "Requested callback", "Third party - patient unavailable"
        return "Other - Third party answered", "Non-patient answered"

    # P6: Language barrier
    lang_phrases = ["russian","russia language","russian speaking","russian translator","no english","no hablo inglés","habla español","do not understand","don't understand english","speak spanish"]
    if has_phrase(ut, lang_phrases):
        return "Other - Language barrier", "Language barrier"
    minimal_spanish = ["aló","alo","hola","allô"]
    if user_words <= 5:
        words = [w.strip(".,!?¿") for w in ut.split()]
        non_greeting = [w for w in words if w and w not in minimal_spanish and w not in ["hello","hello?","hi","hi."]]
        if len(non_greeting) == 0 and len(words) >= 2:
            return "Other - Language barrier", "Possible language barrier (minimal response)"

    # Mixed language with mostly inaudible
    if count_inaudible(ut) >= 2 and user_words <= 10:
        return "Other - No answer/Hangup", "Mostly inaudible / call dropped"

    # P7: Rejected appointment
    reject_own_doctor = ["my own doctor","my doctor","have a doctor","already have a","see my doctor","primary care","otro doctor","ya tengo otro","just came from the","endocrinologist","no longer gonna be making a"]
    reject_not_interested = ["not interested","no thank","don't want","don't need","no thanks","stop calling","don't call","take me off","remove me","leave me alone","do not call","no estoy interesado","i really don't"]
    reject_doesnt_recognize = ["don't recognize","never heard","who is this","what doctor","what clinic","not my doctor","don't know that","never been there","never been to","i don't know who","cuál doctor","don't have an appointment","appointment for what"]
    reject_suspicious = ["scam","spam","fraud","fooling","are you a computer","real person","are you a robot","are you real","is this a recording","recorded line","recording","are you a bot"]
    reject_feels_fine = ["i'm good","feel fine","doing fine","doing good","healthy","feeling good","don't have diabetes","no diabetes","is not diabetic","she don't have that","everything's okay","everything is good","is under control","it's in control"]
    reject_mobility = ["can't walk","cannot walk","can't move","i'm not coming","can't even walk"]

    if has_phrase(ut, reject_own_doctor):
        return "Rejected appointment", "Has own doctor/provider"
    if has_phrase(ut, reject_not_interested):
        return "Rejected appointment", "Not interested"
    if has_phrase(ut, reject_doesnt_recognize):
        return "Rejected appointment", "Doesn't recognize clinic/doctor"
    if has_phrase(ut, reject_suspicious):
        return "Rejected appointment", "Suspicious of call/AI"
    if has_phrase(ut, reject_feels_fine):
        return "Rejected appointment", "Feels fine/Denies condition"
    if has_phrase(ut, reject_mobility):
        return "Rejected appointment", "Can't physically come in/Mobility issues"

    # P8: Requested callback
    cb_busy = ["busy","at work","driving","not a good time","can't talk","i'm working","wrong time","catch me on the wrong time"]
    cb_explicit = ["call me back","call later","call back","let me check","i'll think","check my schedule","think about it","i'll call","give me another call","call me tomorrow","have somebody call me","live person call me","ten minute","tomorrow","i'm sorry"]
    cb_unavail = ["in an appointment","at the doctor","estoy en un appointment","maybe in two hours","should be available"]

    if has_phrase(ut, cb_busy):
        return "Requested callback", "Busy/at work"
    if has_phrase(ut, cb_explicit):
        if has_phrase(at, ["call back","call you back","i'll call","call again","another time"]):
            return "Requested callback", "Requested callback explicitly"
        if has_phrase(ut, ["call me back","call back","call me tomorrow","give me another call"]):
            return "Requested callback", "Requested callback explicitly"
    if has_phrase(ut, cb_unavail):
        return "Requested callback", "Patient unavailable now"

    # Agent confirms callback
    if has_phrase(at, ["i'll call back","call you back tomorrow","call back on"]) and user_words <= 12:
        time_words = ["tomorrow","wednesday","thursday","monday","tuesday","friday","saturday","morning","afternoon","pm","am"]
        if has_phrase(ut, time_words):
            return "Requested callback", "Requested callback explicitly"

    # P8b: Patient wants to speak to front desk / human
    if has_phrase(ut, ["front desk","speak to someone","speak to a person","talk to someone","real person","live person","transfer me"]):
        return "Requested callback", "Wants to speak to live person"

    # P9: No answer / Hangup
    if user_words <= 4:
        return "Other - No answer/Hangup", "No answer or immediate disconnect"
    if user_words <= 10 and user_turns <= 3:
        return "Other - No answer/Hangup", "Minimal response / call dropped"

    # P10: Engaged but inconclusive
    if user_words > 15:
        return "Other - Engaged/Inconclusive", "Patient engaged but no clear outcome"

    # P10b: short but unclear responses (11-15 words)
    if user_words > 10:
        return "Other - Engaged/Inconclusive", "Patient engaged but no clear outcome"

    # P11: Truly unclassifiable
    return "Other - Inconclusive", "Unclassified"
