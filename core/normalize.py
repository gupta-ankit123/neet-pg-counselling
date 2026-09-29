"""Shared normalisation used by the data pipeline and by the app's upload parser."""
import re

STATES = ["Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh",
          "Chhattisgarh", "Dadra and Nagar Haveli", "Daman and Diu", "Delhi", "Goa", "Gujarat", "Haryana",
          "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep",
          "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry",
          "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
          "West Bengal"]
STATE_ALIASES = {"orissa": "Odisha", "pondicherry": "Puducherry", "delhi (nct)": "Delhi", "new delhi": "Delhi",
                 "jammu & kashmir": "Jammu and Kashmir", "uttaranchal": "Uttarakhand",
                 "dadra & nagar haveli": "Dadra and Nagar Haveli", "andaman & nicobar": "Andaman and Nicobar Islands",
                 "dadra & nagar haveli & daman & diu": "Dadra and Nagar Haveli", "chattisgarh": "Chhattisgarh",
                 "tamilnadu": "Tamil Nadu", "telengana": "Telangana",
                 "chhatisgarh": "Chhattisgarh", "dadara nagar haveli": "Dadra and Nagar Haveli",
                 "andaman nicobar islands": "Andaman and Nicobar Islands"}
_STATE_RE = re.compile("|".join(sorted([re.escape(s) for s in STATES] + [re.escape(a) for a in STATE_ALIASES],
                                       key=len, reverse=True)), re.I)

# (regex on compact upper-case course text, branch, clinical type). Order matters.
BRANCH_RULES = [
    (r"^DA$", "Anaesthesiology", "Clinical"),
    (r"^OG$", "Obstetrics & Gynaecology", "Clinical"),
    (r"TRAUMATOLOGY", "Traumatology & Surgery", "Clinical"),
    (r"MPH|EPIDEMI", "Public Health (MPH)", "Para-clinical"),
    (r"PAEDIATRICSURGERY|PEDIATRICSURGERY", "Paediatric Surgery (6 yr)", "Clinical"),
    (r"NEUROSURG", "Neurosurgery (6 yr)", "Clinical"),
    (r"CARDIOVASCULAR|CARDIOTHORACIC|CTVS", "CTVS (6 yr)", "Clinical"),
    (r"PLASTIC", "Plastic Surgery (6 yr)", "Clinical"),
    (r"RADIODIAG|RADIOLOGY|DMRD|MEDICALRADIODIAG", "Radio-Diagnosis", "Clinical"),
    (r"RADIATIONONCO|RADIOONCO|RADIOTHERAPY|DMRT|RADIATIONMED", "Radiation Oncology", "Clinical"),
    (r"NUCLEARMED", "Nuclear Medicine", "Clinical"),
    (r"DERM|VENEREOL|DVL|SKIN", "Dermatology (DVL)", "Clinical"),
    (r"EMERGENCY", "Emergency Medicine", "Clinical"),
    (r"RESPIRATORY|TUBERCULOSIS|CHEST|PULMON|TBCD|DTCD|RESPMED", "Respiratory Medicine", "Clinical"),
    (r"PSYCH", "Psychiatry", "Clinical"),
    (r"FAMILYMED", "Family Medicine", "Clinical"),
    (r"GERIATRIC", "Geriatric Medicine", "Clinical"),
    (r"PALLIATIVE", "Palliative Medicine", "Clinical"),
    (r"PHYSICALMED|PMR|REHAB", "PMR", "Clinical"),
    (r"SPORTSMED", "Sports Medicine", "Clinical"),
    (r"TROPICAL", "Tropical Medicine", "Clinical"),
    (r"INFECTIOUS", "Infectious Diseases", "Clinical"),
    (r"AEROSPACE", "Aerospace Medicine", "Clinical"),
    (r"MARINE", "Marine Medicine", "Clinical"),
    (r"DIABETOLOGY", "Diabetology", "Clinical"),
    (r"FORENSIC|FMT", "Forensic Medicine", "Para-clinical"),
    (r"COMMUNITY|PREVENTIVE|SOCIALMED|PSM|PUBLICHEALTH|COMMMED", "Community Medicine", "Para-clinical"),
    (r"HOSPITALADMIN|HEALTHADMIN|HOSPADMIN", "Hospital Administration", "Non-clinical"),
    (r"IMMUNOHAEM|IMMUNOHEM|TRANSFUS|IHBT", "IHBT (Transfusion Med)", "Para-clinical"),
    (r"MICROBIO|BACTERIO|VIROLOGY", "Microbiology", "Para-clinical"),
    (r"PHARMACOLOGY", "Pharmacology", "Para-clinical"),
    (r"LABORATORYMED|LABMED", "Laboratory Medicine", "Para-clinical"),
    (r"PATHOLOGY", "Pathology", "Para-clinical"),
    (r"ANATOMY", "Anatomy", "Non-clinical"),
    (r"BIOCHEM", "Biochemistry", "Non-clinical"),
    (r"BIOPHYSICS", "Biophysics", "Non-clinical"),
    (r"PHYSIOLOGY", "Physiology", "Non-clinical"),
    (r"ANAES|ANESTH|ANAESTH", "Anaesthesiology", "Clinical"),
    (r"OPHTHAL|DOMS|OPTHAL|EYE", "Ophthalmology", "Clinical"),
    (r"OTORHINO|OTOLARYN|ENT$|^ENT|\bENT\b|DLO", "ENT", "Clinical"),
    (r"ORTHO", "Orthopaedics", "Clinical"),
    (r"OBST|GYNAE|GYNE|GYNEC|OBG|DGO|MATERNITY", "Obstetrics & Gynaecology", "Clinical"),
    (r"PAEDIATRIC|PEDIATRIC|CHILDHEALTH|DCH|PAED", "Paediatrics", "Clinical"),
    (r"GENERALSURGERY|GENSURG|^SURGERY$|MSSURGERY", "General Surgery", "Clinical"),
    (r"GENERALMEDICINE|GENMED|^MEDICINE$|MDMEDICINE|INTERNALMED", "General Medicine", "Clinical"),
]
_BRANCH_RULES = [(re.compile(p), b, c) for p, b, c in BRANCH_RULES]

# MCC short course codes used in the trail columns of the 2025 files
COURSE_CODES = {"GMED": "General Medicine", "GSUR": "General Surgery", "RADD": "Radio-Diagnosis",
                "PAED": "Paediatrics", "OBGY": "Obstetrics & Gynaecology", "ASTH": "Anaesthesiology",
                "BIOC": "Biochemistry", "DERM": "Dermatology (DVL)", "ORTH": "Orthopaedics"}


def compact(s):
    return re.sub(r"[^A-Z]", "", (s or "").upper())


def branch_of(course):
    """-> (branch, clinical_type)"""
    raw = undouble(course or "").upper()
    c = compact(raw)
    if not c:
        return "", ""
    if raw.strip() in COURSE_CODES:
        b = COURSE_CODES[raw.strip()]
        return b, next(ct for _, bb, ct in BRANCH_RULES if bb == b)
    for rx, b, ct in _BRANCH_RULES:
        if rx.search(c) or (b == "ENT" and re.search(r"\bENT\b|E\.N\.T", raw)):
            return b, ct
    return course.strip().title(), "Unknown"


def degree_of(course, seat_type=""):
    u = (course or "").upper() + " " + (seat_type or "").upper()
    if "NBEMS-DIPLOMA" in u.replace(" ", "") or "DNB DIPLOMA" in u or "DNB DIPLIMA" in u or "DNB-DIPLOMA" in u:
        return "DNB Diploma"
    if "6 YEAR" in u or "6 YEARS" in u or "M.CH" in u or "MCH" in u.replace(".", ""):
        return "6-yr Direct"
    if "NBEMS" in u or "DNB" in u:
        return "DNB"
    if re.search(r"\bDIP\b|DIP\.|DIPLOMA|PMN", u):
        return "Diploma"
    if re.search(r"M\.\s*S\.|\bMS\b", u) and not re.search(r"M\.\s*D\.|\bMD\b", u):
        return "MS"
    return "MD" if re.search(r"M\.\s*D\.|\bMD\b", u) else "MD/MS"


def state_of(text):
    """Last state name mentioned in an address string."""
    found = _STATE_RE.findall(text or "")
    if not found:
        return ""
    s = found[-1]
    return STATE_ALIASES.get(s.lower(), next((x for x in STATES if x.lower() == s.lower()), s))


def institute_name(raw):
    """MCC institute strings look like 'Name,Name, address..., State, 123456'. Return a short display name."""
    s = re.sub(r"\s+", " ", (raw or "")).strip().strip(",")
    if not s or s == "-":
        return ""
    head = s[:18].upper()
    p = s.upper().find(head, 5) if len(head) >= 8 else -1
    if p > 0:
        s = s[:p]
    else:
        s = re.sub(r",?\s*\d{6}\s*$", "", s)
        st = state_of(s)
        if st:
            s = re.sub(r",\s*(%s)\s*,?\s*$" % re.escape(st), "", s, flags=re.I)
        first = s.split(",")[0].strip()
        if re.search(r"COLLEGE|INSTITUTE|HOSPITAL|UNIVERSITY|CENTRE|CENTER|ACADEMY|SCIENCES", first.upper()):
            s = first
    s = re.sub(r"[\s,]+$", "", s)
    s = re.sub(r"\s*,\s*,", ",", s)
    return s[:120]


def name_key(name):
    s = (name or "").upper()
    s = re.sub(r"\bGOVT\b\.?", "GOVERNMENT", s)
    s = re.sub(r"\bMED(ICAL)?\.?\s*COLL(EGE)?\b", "MEDICAL COLLEGE", s)
    s = s.replace("&", " AND ")
    return re.sub(r"[^A-Z0-9]", "", s)


QUOTA_MAP = {
    "AI": ("AIQ", "All India Quota"), "ALL INDIA": ("AIQ", "All India Quota"),
    "AD": ("DNB", "DNB Quota"), "DNB QUOTA": ("DNB", "DNB Quota"),
    "PS": ("DEEMED", "Deemed/Paid Seat"), "SELF-FINANCED MERIT SEAT": ("DEEMED", "Deemed/Paid Seat"),
    "SELF- FINANCED MERIT SEAT": ("DEEMED", "Deemed/Paid Seat"),
    "SELF-FINANCED MERIT SEAT/(PAID SEAT QUOTA)": ("DEEMED", "Deemed/Paid Seat"),
    "MANAGEMENT/PAID SEATS QUOTA": ("DEEMED", "Deemed/Paid Seat"), "MANAGEME NT/PAID SEATS QUOTA": ("DEEMED", "Deemed/Paid Seat"),
    "NR": ("NRI", "NRI"), "NON-RESIDENT INDIAN": ("NRI", "NRI"), "NON-RESIDEN T INDIAN": ("NRI", "NRI"),
    "DU": ("DU", "Delhi University"), "DELHI UNIVERSITY QUOTA": ("DU", "Delhi University"),
    "IP": ("IPU", "IP University"), "IP UNIVERSITY QUOTA": ("IPU", "IP University"),
    "AM": ("AMU", "Aligarh Muslim Univ"), "ALIGARH MUSLIM UNIVERSITY": ("AMU", "Aligarh Muslim Univ"),
    "BH": ("BHU", "Banaras Hindu Univ"), "BANARAS HINDU UNIVERSITY": ("BHU", "Banaras Hindu Univ"),
    "AF": ("AFMS", "Armed Forces"), "ARMED FORCES MEDICAL": ("AFMS", "Armed Forces"),
    "MM": ("MINORITY", "Muslim Minority"), "MUSLIM MINORITY QUOTA": ("MINORITY", "Muslim Minority"),
    "JM": ("MINORITY", "Jain Minority"), "JAIN MINORITY QUOTA": ("MINORITY", "Jain Minority"),
    "ESI": ("ESI", "ESI Insured"),
}


_QUOTA_COMPACT = {re.sub(r"[^A-Z]", "", k): v for k, v in QUOTA_MAP.items()}


def quota_of(q):
    k = re.sub(r"\s+", " ", (q or "").upper()).strip()
    if k in QUOTA_MAP:
        return QUOTA_MAP[k]
    ck = re.sub(r"[^A-Z]", "", k)
    if ck in _QUOTA_COMPACT:
        return _QUOTA_COMPACT[ck]
    if "EMPLOYEESSTATEINSURANCE" in re.sub(r"[^A-Z]", "", k) or "ESI" in k:
        return ("ESI", "ESI Insured")
    if "PAID" in ck or "SELF" in ck or "MANAGEMENT" in ck:
        return ("DEEMED", "Deemed/Paid Seat")
    if "NRI" in ck or "NONRES" in ck:
        return ("NRI", "NRI")
    return (k[:12], q or "")


def category_of(cat):
    """-> (base category, pwd flag). Handles MCC ('Open PwD', 'GNYes') and state ('UR','EB','BC') styles."""
    c = re.sub(r"\s+", " ", undouble(cat or "").upper()).strip()
    pwd = "PWD" in c or c.endswith("YES") or c in ("PH", "DQ")
    c = c.replace("PWD", "").replace("YES", "").strip()
    table = {"OPEN": "Open", "GN": "Open", "GENERAL": "Open", "UR": "Open", "UNRESERVED": "Open", "GEN": "Open",
             "EWS": "EWS", "EW": "EWS", "ES": "EWS", "GENERAL-EWS": "EWS",
             "OBC": "OBC", "BC": "OBC", "SEBC": "OBC", "OBC-NCL": "OBC",
             "EBC": "EBC", "EB": "EBC", "SC": "SC", "ST": "ST", "RCG": "Open", "GC": "Green Card", "PH": "Open",
             "DQ": "Open", "NRI": "Open", "MM": "Open", "SM": "Open", "GCH": "Green Card",
             "GREEN CARD": "Green Card"}
    return table.get(c, c.title() if c else ""), pwd


GOVT_HINTS = re.compile(r"GOVT|GOVERNMENT|DISTRICT|CIVIL HOSP|SADAR|MUNICIPAL|ESIC|E\.S\.I|EMPLOYEES STATE|RAILWAY|"
                        r"STATE |GENERAL HOSPITAL|REFERRAL|HEADQUARTER|\bDHH\b|\bRGH\b|AREA HOSPITAL|SUB DIVISIONAL|"
                        r"CORPORATION|NAVAL|ARMY|AIR FORCE|COMMAND HOSPITAL|INSTITUTE OF MEDICAL SCIENCES|AIIMS|"
                        r"PGIMER|MEDICAL COLLEGE AND HOSPITAL|RMLIMS|CAPITAL HOSPITAL|LNJP|PHC|CHC")


def dnb_hospital_type(name):
    return "Govt" if GOVT_HINTS.search((name or "").upper()) else "Private"


def clean_remark(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    s = s.replace("Upgradati on", "Upgradation").replace("3nd", "3rd").replace("Allotted( ", "Allotted (")
    return s


def undouble(s):
    """'Ddeeggrreeee' -> 'Degree' (bold text that the PDF extractor read twice)."""
    def one(w):
        if len(w) >= 4 and len(w) % 2 == 0 and all(w[i].lower() == w[i + 1].lower() for i in range(0, len(w), 2)):
            return w[::2]
        return w
    return " ".join(one(w) for w in (s or "").split(" "))


_STATUS = {"REPORTED": "Reported", "NOTREPORTED": "Not Reported", "SEATSURRENDERED": "Seat Surrendered",
           "SEATCANCELLED": "Seat Cancelled", "FRESHALLOTMENT": "Fresh Allotment", "SEATRETAINED": "Seat Retained",
           "SEATUPGRADE": "Seat Upgrade"}


def clean_status(s):
    s = undouble(re.sub(r"\s+", " ", s or "").strip())
    return _STATUS.get(re.sub(r"[^A-Z]", "", s.upper()), s)
