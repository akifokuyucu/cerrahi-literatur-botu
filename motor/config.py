"""
Cerrahi Literatür Botu — yapılandırma.

Bu dosya botun "zevkini" belirler: hangi dergiye ne kadar güvendiğimiz,
hangi çalışma tipinin ne kadar ağır bastığı ve her alt alanın nasıl arandığı.
Kod bilmeden de düzenlenebilecek şekilde sade tutuldu.

Dergi adları PubMed'in NLM kısaltmalarıdır (MedlineTA). Karşılaştırma
büyük/küçük harf ve noktalama duyarsızdır.
"""

# ---------------------------------------------------------------------------
# 1) DERGİ KADEMELERİ (tüm alanlar için ortak)
# ---------------------------------------------------------------------------
DERGI_PUANI = {"kademe1": 3, "kademe2": 2, "kademe3": 1, "listede_yok": 0}

ORTAK_DERGILER = {
    "kademe1": ["N Engl J Med", "Lancet", "JAMA", "BMJ", "Nat Med"],
    "kademe2": ["Ann Surg", "JAMA Surg", "Br J Surg", "J Am Coll Surg"],
    "kademe3": ["Surgery", "World J Surg", "Surg Endosc",
                "Langenbecks Arch Surg", "JAMA Netw Open"],
}

# ---------------------------------------------------------------------------
# 2) ÇALIŞMA TİPİ PUANLARI
# ---------------------------------------------------------------------------
TIP_PUANI = {
    "kilavuz": 4,        # Kılavuz / konsensus
    "meta_analiz": 3,    # Meta-analiz / sistematik derleme
    "rct": 3,            # Randomize kontrollü çalışma
    "prospektif": 2,     # Prospektif / çok merkezli kohort
    "diger": 1,          # Retrospektif, derleme ve diğer özgün çalışmalar
}

TIP_ETIKETI = {
    "kilavuz": "📘 Kılavuz/Konsensus",
    "meta_analiz": "🟢 Meta-analiz",
    "rct": "🟢 RCT",
    "prospektif": "🟡 Prospektif",
    "diger": "⚪ Retrospektif/Diğer",
}

# Bu yayın tipleri listeye hiç girmez.
ELENEN_TIPLER = [
    "Case Reports", "Editorial", "Comment", "Letter", "News",
    "Published Erratum", "Retraction Notice", "Retracted Publication",
    "Biography", "Interview", "Video-Audio Media", "Conference Proceedings",
    "Congress",
]

# ---------------------------------------------------------------------------
# 3) TÜRK DERGİSİ (puanlamaya girmez, listenin altında ayrı satır)
# ---------------------------------------------------------------------------
TURK_DERGISI = "Turk J Surg"
TURK_DERGISI_GERIYE_GUN = 200  # üç ayda bir çıktığı için geniş pencere

# ---------------------------------------------------------------------------
# 4) ALT ALANLAR
#    ad        : Telegram'da görünen buton adı
#    anahtar   : başlık/özette aranan terimler (herhangi biri)
#    cerrahi   : cerrahi bağlam terimleri (anahtar ile birlikte en az biri);
#                None ise cerrahi bağlam şartı aranmaz
#    ust       : bu alan için Kademe 1 puanı alan dergiler
#    alan_dergileri : bu alan için Kademe 3 puanı alan dergiler; bu
#                dergilerdeki makaleler terim şartı olmadan alana girer
# ---------------------------------------------------------------------------
CERRAHI_BAGLAM = [
    "surg*", "resection*", "operative", "operation*", "laparoscop*",
    "robotic", "minimally invasive", "anastomo*", "postoperative",
    "perioperative",
]

ALANLAR = {
    "kolorektal": {
        "ad": "Kolorektal",
        "anahtar": [
            "colorectal", "rectal cancer", "rectal neoplasm*", "colon cancer",
            "colonic", "colectomy", "proctectomy", "mesorectal",
            "diverticulitis", "anastomotic leak*", "ileal pouch",
            "ileostomy", "colostomy", "hemorrhoid*", "haemorrhoid*",
            "anal fistula", "pilonidal", "watch and wait",
            "total neoadjuvant",
        ],
        "cerrahi": CERRAHI_BAGLAM,
        "ust": ["Gut", "Lancet Gastroenterol Hepatol"],
        "alan_dergileri": ["Dis Colon Rectum", "Colorectal Dis",
                           "Tech Coloproctol", "Int J Colorectal Dis"],
    },
    "hepatobilier": {
        "ad": "Hepatobilier",
        "anahtar": ["hepatectomy", "liver resection", "hepatic resection",
                    "hepatocellular carcinoma", "colorectal liver metastas*",
                    "cholangiocarcinoma", "bile duct injur*",
                    "cholecystectomy", "gallbladder cancer", "ALPPS",
                    "biliary"],
        "cerrahi": CERRAHI_BAGLAM,
        "ust": ["J Hepatol", "Hepatology"],
        "alan_dergileri": ["HPB (Oxford)", "J Hepatobiliary Pancreat Sci"],
    },
    "pankreas": {
        "ad": "Pankreas",
        "anahtar": ["pancreatic cancer", "pancreatic ductal adenocarcinoma",
                    "pancreatoduodenectomy", "pancreaticoduodenectomy",
                    "Whipple", "distal pancreatectomy", "pancreatic fistula",
                    "pancreatectomy", "IPMN", "pancreatitis"],
        "cerrahi": CERRAHI_BAGLAM,
        "ust": ["Gastroenterology"],
        "alan_dergileri": ["Pancreatology", "Pancreas"],
    },
    "ust_gis": {
        "ad": "Üst GİS",
        "anahtar": ["gastric cancer", "gastrectomy", "esophagectomy",
                    "oesophagectomy", "esophageal cancer",
                    "oesophageal cancer", "fundoplication", "achalasia",
                    "POEM", "hiatal hernia", "gastroesophageal reflux"],
        "cerrahi": CERRAHI_BAGLAM,
        "ust": ["Gastroenterology"],
        "alan_dergileri": ["Gastric Cancer", "Dis Esophagus",
                           "J Gastrointest Surg"],
    },
    "bariatrik": {
        "ad": "Bariatrik",
        "anahtar": ["bariatric", "metabolic surgery", "sleeve gastrectomy",
                    "gastric bypass", "one anastomosis gastric bypass",
                    "obesity surgery"],
        "cerrahi": None,
        "ust": ["Lancet Diabetes Endocrinol"],
        "alan_dergileri": ["Obes Surg", "Surg Obes Relat Dis"],
    },
    "meme": {
        "ad": "Meme",
        "anahtar": ["breast cancer", "breast surgery", "mastectomy",
                    "breast-conserving", "sentinel lymph node",
                    "axillary", "oncoplastic"],
        "cerrahi": CERRAHI_BAGLAM + ["axillary", "sentinel", "mastectomy"],
        "ust": ["J Clin Oncol", "Lancet Oncol", "JAMA Oncol"],
        "alan_dergileri": ["Ann Surg Oncol", "Breast",
                           "Breast Cancer Res Treat"],
    },
    "herni": {
        "ad": "Herni & Karın Duvarı",
        "anahtar": ["hernia*", "hernioplasty", "herniorrhaphy",
                    "abdominal wall reconstruction", "eTEP", "TAPP",
                    "incisional hernia", "inguinal hernia", "ventral hernia"],
        "cerrahi": None,
        "ust": [],
        "alan_dergileri": ["Hernia", "J Abdom Wall Surg"],
    },
    "transplantasyon": {
        "ad": "Transplantasyon",
        # Yalnızca BAŞLIKTA aranır: özette "transplant" geçen hepatoloji/
        # nefroloji makaleleri bu alana sızmasın
        "anahtar_etiket": "ti",
        "anahtar": ["liver transplant*", "kidney transplant*",
                    "renal transplant*", "pancreas transplant*",
                    "living donor*", "machine perfusion",
                    "donation after circulatory death", "deceased donor*",
                    "graft failure", "hepatic artery thrombosis"],
        "cerrahi": None,
        "ust": ["J Hepatol"],
        "alan_dergileri": ["Am J Transplant", "Transplantation",
                           "Liver Transpl", "Transpl Int"],
    },
    "onkoloji": {
        "ad": "Onkoloji",
        "anahtar": ["peritoneal metastas*", "peritoneal carcinomatosis",
                    "HIPEC", "PIPAC", "cytoreductive surgery",
                    "pseudomyxoma", "sarcoma", "retroperitoneal",
                    "melanoma", "GIST", "gastrointestinal stromal"],
        "cerrahi": CERRAHI_BAGLAM + ["cytoreductive", "HIPEC", "PIPAC"],
        "ust": ["J Clin Oncol", "Lancet Oncol", "JAMA Oncol"],
        "alan_dergileri": ["Pleura Peritoneum"],
    },
    "acil": {
        "ad": "Acil Cerrahi",
        "anahtar": ["emergency surgery", "emergency general surgery",
                    "acute appendicitis", "appendectomy",
                    "acute cholecystitis", "small bowel obstruction",
                    "perforat*", "acute care surgery", "trauma laparotomy",
                    "damage control", "REBOA"],
        "cerrahi": None,
        "ust": [],
        "alan_dergileri": ["World J Emerg Surg", "J Trauma Acute Care Surg",
                           "Eur J Trauma Emerg Surg"],
    },
    "mis": {
        "ad": "MIS, Robotik & Endoskopi",
        "anahtar": ["robotic surgery", "robot-assisted", "robotic-assisted",
                    "laparoscopic", "minimally invasive surgery",
                    "endoscopic submucosal dissection", "ERCP",
                    "endoscopic", "natural orifice"],
        "cerrahi": CERRAHI_BAGLAM + ["endoscop*"],
        "ust": ["Endoscopy", "Gastrointest Endosc"],
        "alan_dergileri": ["J Robot Surg", "J Laparoendosc Adv Surg Tech A",
                           "Surg Laparosc Endosc Percutan Tech"],
    },
    "egitim": {
        "ad": "Eğitim & Simülasyon",
        "anahtar": ["surgical education", "surgical training",
                    "residency", "resident*", "simulation", "curriculum",
                    "learning curve", "competency"],
        "cerrahi": ["surg*"],
        "ust": ["Acad Med", "Med Educ"],
        "alan_dergileri": ["J Surg Educ", "Simul Healthc"],
    },
    "yapay_zeka": {
        "ad": "AI & Dijital Cerrahi",
        "anahtar": ["artificial intelligence", "machine learning",
                    "deep learning", "large language model*", "ChatGPT",
                    "computer vision", "digital surgery", "surgical video"],
        "cerrahi": ["surg*", "operative", "postoperative"],
        "ust": ["Lancet Digit Health", "NPJ Digit Med"],
        "alan_dergileri": ["Int J Comput Assist Radiol Surg"],
    },
    "enfeksiyon": {
        "ad": "Cerrahi Enfeksiyonlar",
        "anahtar": ["surgical site infection*", "wound infection",
                    "antibiotic prophylaxis", "intra-abdominal infection*",
                    "postoperative infection*"],
        "cerrahi": None,
        "ust": ["Lancet Infect Dis", "Clin Infect Dis"],
        "alan_dergileri": ["Surg Infect (Larchmt)", "J Hosp Infect",
                           "Infect Control Hosp Epidemiol"],
    },
}

# Genel cerrahi dışı branşlar: başlığında bunlar geçen makaleler hiçbir
# alana girmez (ör. robotik diz protezi, jinekolojik onkoloji)
DIGER_BRANSLAR = [
    "arthroplasty", "knee", "hip fracture", "spine", "spinal",
    "prostatectomy", "prostate", "hysterectomy", "gynecolog*",
    "gynaecolog*", "ovarian", "endometri*", "cervical cancer", "urolog*",
    "bladder cancer", "cystectomy", "cardiac surgery", "coronary",
    "aortic valve", "mitral", "lung cancer", "lobectomy", "pneumonectomy",
    "thoracic surgery", "neurosurg*", "craniotomy", "cataract", "retina*",
    "dental", "orthodont*", "tonsillectomy", "rhinoplasty", "cesarean",
    "caesarean",
]

# Her alanda gösterilecek makale sayısı
ALAN_BASINA = 5
# Kaç günlük pencere taransın
PENCERE_GUN = 7
