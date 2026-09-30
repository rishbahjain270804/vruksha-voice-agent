"""Data shapes. The transcript is source data — it is a plain string that only the
speech-to-text layer ever writes. Nothing downstream (LLM, assembler) may alter it."""
from __future__ import annotations
from pydantic import BaseModel
from typing import List, Optional, Literal

# One place that knows about a language. STT (Whisper), the LLM planner, and ElevenLabs TTS are all
# multilingual, so a new language is just another entry here + its prompt strings. `{t}`/`{list}` are
# filled at runtime. To add e.g. Telugu: copy a block, translate the strings, set whisper/sr codes.
LANGUAGES = {
    "en": {
        "native": "English", "whisper": "en", "sr": "en-US", "llm": "English",
        "opener": "What do you want to log today? Just tell me what you worked on.",
        "yes": {"yes", "yeah", "yep", "post it", "post", "sure", "okay", "ok"},
        "no": {"no", "nope", "don't", "dont", "stop", "cancel"},
        "pick_one": "Is this a continuation of “{t}”, or something new?",
        "pick_many": "Which project is this — {list}? Or say it's something new.",
        "link": "Earlier you logged about {t}. Is today part of that same work? Say yes or no.",
        "confirm_pre": "Here is what I will post. ",
        "confirm_post": " Should I post it? Say yes or no.",
        "cont_tag": "(Continuing: {t}) ",
    },
    "ta": {
        "native": "தமிழ்", "whisper": "ta", "sr": "ta-IN", "llm": "Tamil",
        "opener": "இன்று எதைப் பதிவு செய்ய விரும்புகிறீர்கள்? நீங்கள் எதில் வேலை செய்தீர்கள் என்று சொல்லுங்கள்.",
        "yes": {"ஆம்", "சரி", "போடு", "podu", "post pannu", "yes", "ok"},
        "no": {"இல்லை", "வேண்டாம்", "no", "stop"},
        "pick_one": "இது “{t}” வேலையின் தொடர்ச்சியா, அல்லது புதிதா?",
        "pick_many": "எந்த வேலை இது — {list}? அல்லது புதிது என்று சொல்லுங்கள்.",
        "link": "முன்பு நீங்கள் {t} பற்றி பதிவு செய்தீர்கள். இது அதன் தொடர்ச்சியா? ஆம் அல்லது இல்லை.",
        "confirm_pre": "நான் இதை பதிவு செய்யப் போகிறேன். ",
        "confirm_post": " பதிவு செய்யட்டுமா? ஆம் அல்லது இல்லை என்று சொல்லுங்கள்.",
        "cont_tag": "({t} தொடர்ச்சி) ",
    },
    "hi": {
        "native": "हिन्दी", "whisper": "hi", "sr": "hi-IN", "llm": "Hindi",
        "opener": "आज आप क्या लॉग करना चाहते हैं? बस बताइए आपने किस पर काम किया।",
        "yes": {"हाँ", "हां", "जी", "ठीक", "पोस्ट", "करो", "yes", "ok"},
        "no": {"नहीं", "ना", "मत", "रुको", "रद्द", "no", "stop"},
        "pick_one": "क्या यह “{t}” का ही सिलसिला है, या कुछ नया?",
        "pick_many": "यह कौन-सा प्रोजेक्ट है — {list}? या कहिए कि यह नया है।",
        "link": "पहले आपने {t} के बारे में लॉग किया था। क्या आज का काम उसी का हिस्सा है? हाँ या नहीं कहिए।",
        "confirm_pre": "मैं यह पोस्ट करने जा रहा हूँ। ",
        "confirm_post": " क्या मैं इसे पोस्ट करूँ? हाँ या नहीं कहिए।",
        "cont_tag": "({t} जारी) ",
    },
    "te": {
        "native": "తెలుగు", "whisper": "te", "sr": "te-IN", "llm": "Telugu",
        "opener": "నేడు మీరు ఏమి లాగ్ చేయాలనుకుంటున్నారు? మీరు ఏ పని చేసారో చెప్పండి.",
        "yes": {"అవును", "సరే", "ఖచ్చితంగా", "నిశ్చయంగా", "అవును చేయండి", "ok"},
        "no": {"కాదు", "లేదు", "అవసరం లేదు", "ఇప్పుడే కాదు", "వద్దు", "no"},
        "pick_one": 'ఇది "{t}" యొక్క కొనసాగింపా, లేక కొత్తదా?',
        "pick_many": "ఇది ఏ ప్రాజెక్టు — {list}? లేక ఇది కొత్తదని చెప్పండి.",
        "link": "ముందుగా మీరు {t} గురించి లాగ్ చేశారు. నేడు కూడా అదే పనిలో భాగమా? అవును లేదా కాదు చెప్పండి.",
        "confirm_pre": "ఇది నేను పోస్ట్ చేయబోయే విషయం. ",
        "confirm_post": " దాన్ని పోస్ట్ చేయాలా? అవును లేదా కాదు చెప్పండి.",
        "cont_tag": "(కొనసాగింపు: {t}) ",
    },
    "kn": {
        "native": "ಕನ್ನಡ", "whisper": "kn", "sr": "kn-IN", "llm": "Kannada",
        "opener": "ಇಂದು ನೀವು ಏನು ಲಾಗ್ ಮಾಡಬೇಕು? ನೀವು ಏನು ಕೆಲಸ ಮಾಡಿದ್ದೀರಿ ಎಂದು ಹೇಳಿ.",
        "yes": {"ಹೌದು", "ಸರಿ", "ಖಂಡಿತ", "ನಿಶ್ಚಯವಾಗಿ", "ಅವಶ್ಯ", "ok"},
        "no": {"ಇಲ್ಲ", "ಅಲ್ಲ", "ಸಾಧ್ಯವಿಲ್ಲ", "ಬೇಡ", "ನಿಲ್ಲಿಸಿ", "no"},
        "pick_one": 'ಇದು "{t}" ನ ಮುಂದುವರಿಕೆಯಾ, ಇಲ್ಲವೇ ಹೊಸದಾ?',
        "pick_many": "ಇದು ಯಾವ ಪ್ರಾಜೆಕ್ಟ್ — {list}? ಇಲ್ಲವೇ ಇದು ಹೊಸದಾಗಿದೆ ಎಂದು ಹೇಳಿ.",
        "link": "ಹಿಂದೆ ನೀವು {t} ಬಗ್ಗೆ ಲಾಗ್ ಮಾಡಿದ್ದೀರಿ. ಇಂದಿನ ಕೆಲಸವೂ ಅದೇ ಕೆಲಸದ ಭಾಗವೇ? ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಹೇಳಿ.",
        "confirm_pre": "ಇದು ನಾನು ಪೋಸ್ಟ್ ಮಾಡಲಿರುವುದು. ",
        "confirm_post": " ಇದನ್ನು ಪೋಸ್ಟ್ ಮಾಡಬೇಕೆ? ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಹೇಳಿ.",
        "cont_tag": "(ಮುಂದುವರಿಕೆ: {t}) ",
    },
    "ml": {
        "native": "മലയാളം", "whisper": "ml", "sr": "ml-IN", "llm": "Malayalam",
        "opener": "ഇന്ന് നിങ്ങൾ എന്താണ് ലോഗ് ചെയ്യാൻ ആഗ്രഹിക്കുന്നത്? നിങ്ങൾ ചെയ്തതെല്ലാം പറയൂ.",
        "yes": {"അതെ", "ശരി", "തീർച്ചയായും", "അതെ ചെയ്യാം", "ഒക്കെ", "ok"},
        "no": {"ഇല്ല", "വേണ്ട", "ഒരിക്കലുമില്ല", "അല്ല", "നിർത്തൂ", "no"},
        "pick_one": 'ഇത് "{t}" എന്നതിന്റെ തുടർച്ചയാണോ, അല്ലെങ്കിൽ പുതിയതോ?',
        "pick_many": "ഇത് ഏത് പ്രോജക്റ്റാണ് — {list}? അല്ലെങ്കിൽ പുതിയതാണെന്ന് പറയൂ.",
        "link": "മുമ്പ് നിങ്ങൾ {t} എന്നതിനെക്കുറിച്ച് ലോഗ് ചെയ്തിരുന്നു. ഇന്നത്തെ ജോലി അതേ ജോലിയുടെ ഭാഗമാണോ? അതെ അല്ലെങ്കിൽ ഇല്ല എന്ന് പറയൂ.",
        "confirm_pre": "ഇതാണ് ഞാൻ പോസ്റ്റ് ചെയ്യാൻ പോകുന്നത്. ",
        "confirm_post": " ഞാൻ ഇത് പോസ്റ്റ് ചെയ്യണോ? അതെ അല്ലെങ്കിൽ ഇല്ല എന്ന് പറയൂ.",
        "cont_tag": "(തുടരുന്നു: {t}) ",
    },
    "bn": {
        "native": "বাংলা", "whisper": "bn", "sr": "bn-IN", "llm": "Bengali",
        "opener": "আজ আপনি কী লগ করতে চান? শুধু আমাকে বলুন আপনি কী কাজ করেছেন।",
        "yes": {"হ্যাঁ", "অবশ্যই", "নিশ্চয়ই", "ঠিক আছে", "হ্যাঁ করুন", "ok"},
        "no": {"না", "নিশ্চয় নয়", "একদম না", "বাদ দিন", "থামুন", "no"},
        "pick_one": 'এটি কি "{t}" এর ধারাবাহিকতা, নাকি কিছু নতুন?',
        "pick_many": "এটি কোন প্রকল্প — {list}? অথবা বলুন এটি কিছু নতুন।",
        "link": "আগে আপনি {t} সম্পর্কে লগ করেছেন। আজকের কাজ কি একই কাজের অংশ? হ্যাঁ বা না বলুন।",
        "confirm_pre": "এটি আমি পোস্ট করব। ",
        "confirm_post": " আমি কি এটি পোস্ট করব? হ্যাঁ বা না বলুন।",
        "cont_tag": "(চলমান: {t}) ",
    },
    "mr": {
        "native": "मराठी", "whisper": "mr", "sr": "mr-IN", "llm": "Marathi",
        "opener": "आज तुम्ही काय लॉग करायचे आहे? फक्त मला सांगा तुम्ही काय काम केले.",
        "yes": {"होय", "हो", "नक्कीच", "बरोबर", "ठीक आहे", "ok"},
        "no": {"नाही", "नको", "रद्द करा", "थांबा", "नक्की नाही", "no"},
        "pick_one": 'हे "{t}" चे पुढे चालू आहे का, की काही नवीन आहे?',
        "pick_many": "हे कोणत्या प्रोजेक्टचे आहे — {list}? किंवा हे काही नवीन आहे असं सांगा.",
        "link": "तुम्ही आधी {t} बद्दल लॉग केले होते. आजचे काम त्याच कामाचा भाग आहे का? होय किंवा नाही सांगा.",
        "confirm_pre": "हे मी पोस्ट करणार आहे. ",
        "confirm_post": " मी हे पोस्ट करावे का? होय किंवा नाही सांगा.",
        "cont_tag": "(सुरू: {t}) ",
    },
    "gu": {
        "native": "ગુજરાતી", "whisper": "gu", "sr": "gu-IN", "llm": "Gujarati",
        "opener": "આજે તમે શું લોગ કરવું માંગો છો? માત્ર મને કહો કે તમે શું કર્યું.",
        "yes": {"હા", "બિલકુલ", "સાચું છે", "ઠીક છે", "ચોક્કસ", "ok"},
        "no": {"ના", "નહીં", "રદ કરો", "રહેવા દો", "ના જોઈએ", "no"},
        "pick_one": 'શું આ "{t}" નું ચાલુ છે, કે કંઈક નવું?',
        "pick_many": "આ કયું પ્રોજેક્ટ છે — {list}? અથવા કહો કે આ કંઈક નવું છે.",
        "link": "પહેલાં તમે {t} વિશે લોગ કર્યું હતું. શું આજે પણ એ જ કામનો ભાગ છે? હા કે ના કહો.",
        "confirm_pre": "આ હું પોસ્ટ કરવા જઈ રહ્યો છું. ",
        "confirm_post": " શું હું તેને પોસ્ટ કરું? હા કે ના કહો.",
        "cont_tag": "(ચાલુ: {t}) ",
    },
    "pa": {
        "native": "ਪੰਜਾਬੀ", "whisper": "pa", "sr": "pa-IN", "llm": "Punjabi",
        "opener": "ਅੱਜ ਤੁਸੀਂ ਕੀ ਲਾਗ ਕਰਨਾ ਚਾਹੁੰਦੇ ਹੋ? ਸਿਰਫ਼ ਦੱਸੋ ਤੁਸੀਂ ਕੀ ਕੀਤਾ।",
        "yes": {"ਹਾਂ", "ਜੀ ਹਾਂ", "ਬਿਲਕੁਲ", "ਜ਼ਰੂਰ", "ਠੀਕ ਹੈ", "ok"},
        "no": {"ਨਹੀਂ", "ਜੀ ਨਹੀਂ", "ਬਿਲਕੁਲ ਨਹੀਂ", "ਰੱਦ ਕਰੋ", "ਨਾ", "no"},
        "pick_one": 'ਕੀ ਇਹ "{t}" ਦੀ ਜਾਰੀ ਹੈ, ਜਾਂ ਕੁਝ ਨਵਾਂ ਹੈ?',
        "pick_many": "ਇਹ ਕਿਹੜਾ ਪ੍ਰੋਜੈਕਟ ਹੈ — {list}? ਜਾਂ ਕਹੋ ਕਿ ਇਹ ਕੁਝ ਨਵਾਂ ਹੈ।",
        "link": "ਪਹਿਲਾਂ ਤੁਸੀਂ {t} ਬਾਰੇ ਲਾਗ ਕੀਤਾ ਸੀ। ਕੀ ਅੱਜ ਵੀ ਉਹੀ ਕੰਮ ਹੈ? ਹਾਂ ਜਾਂ ਨਹੀਂ ਕਹੋ।",
        "confirm_pre": "ਇਹ ਹੈ ਜੋ ਮੈਂ ਪੋਸਟ ਕਰਾਂਗਾ। ",
        "confirm_post": " ਕੀ ਮੈਂ ਇਹ ਪੋਸਟ ਕਰਾਂ? ਹਾਂ ਜਾਂ ਨਹੀਂ ਕਹੋ।",
        "cont_tag": "(ਜਾਰੀ: {t}) ",
    },
}
DEFAULT_LANG = "en"


def lang_cfg(lang: str) -> dict:
    return LANGUAGES.get(lang, LANGUAGES[DEFAULT_LANG])


class Answer(BaseModel):
    question: str
    transcript: str  # raw, word-for-word, never rewritten


class ConversationState(BaseModel):
    session_id: str
    lang: str = DEFAULT_LANG
    stage: Literal["greet", "pick", "ask", "link", "confirm", "posted", "cancelled"] = "greet"
    answers: List[Answer] = []
    followup_question: Optional[str] = None
    # continuity: does today continue an earlier log?
    topic_candidates: Optional[list] = None  # earlier projects to disambiguate between ("which one?")
    related_topic: Optional[dict] = None   # candidate found from history
    continues: Optional[dict] = None       # set to related_topic if the student says yes
    # built only at the confirm stage, from raw transcripts:
    draft_verb: Optional[str] = None
    draft_content: Optional[str] = None
    draft_why: Optional[str] = None
    post_result: Optional[dict] = None


class PostLog(BaseModel):
    verb: str
    content: str
    why: str


class AnswerIn(BaseModel):
    # Either a text transcript (browser STT / typing) or the server transcribed audio upstream.
    transcript: str


class ConfirmIn(BaseModel):
    utterance: str  # what the student said at the confirm step; classified into yes/no here
