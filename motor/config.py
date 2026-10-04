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
# Bazı alanlarda ek Türk dergileri (TJTES aylık çıkar)
ALAN_TURK_DERGILERI = {
    "acil": ["Turk J Surg", "Ulus Travma Acil Cerrahi Derg"],
}
TUM_TURK_DERGILERI = {TURK_DERGISI} | {
    d for liste in ALAN_TURK_DERGILERI.values() for d in liste}


def turk_dergileri(alan_kodu):
    return ALAN_TURK_DERGILERI.get(alan_kodu, [TURK_DERGISI])

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
                    "damage control", "REBOA", "abdominal trauma",
                    "blunt trauma", "penetrating trauma", "splenic trauma",
                    "splenic injur*", "liver trauma", "hepatic trauma",
                    "incarcerated"],
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
    "caesarean", "orbit*", "ocular", "uveal", "conjunctiv*", "eyelid",
    "uterine", "uterus", "cervix", "vulvar", "pyeloplasty", "hypospadias",
    "nephrolithotomy", "ureteroscopy", "laryn*", "head and neck",
]

# Geniş kapsamlı dergiler: puan alırlar ama makaleleri alana OTOMATİK
# girmez; yalnızca alanın terimleriyle eşleşen makaleleri alınır
GENIS_DERGILER = [
    "Ann Surg Oncol", "Eur J Surg Oncol", "J Surg Oncol", "J Gastrointest Surg",
    "J Hosp Infect", "Infect Control Hosp Epidemiol", "Transplantation",
    "Int J Comput Assist Radiol Surg", "Surg Laparosc Endosc Percutan Tech",
    "J Laparoendosc Adv Surg Tech A", "J Robot Surg", "HPB (Oxford)",
]

# Her alanda gösterilecek makale sayısı
ALAN_BASINA = 5
# Kişisel puan: bottaki 👍/👎 oylarından dergi ve çalışma tipi başına
# en fazla ±0,5 (toplam ±1) katkı. Her net oy 0,25 puan.
KISISEL_ADIM = 0.25
KISISEL_SINIR = 0.5
BOT_URL = "https://cerrahi-literatur-botu.akif-okuyucu.workers.dev"

# Cerrahi ilgi kontrolü için yapay zekâya gönderilen aday sayısı
ADAY_SAYISI = 12
# Kısa özet isteği başına en fazla makale (12 aday + Türk dergisi → 7 + 6)
OZET_PARTI = 7
# Kaç günlük pencere taransın
PENCERE_GUN = 7
# Ayrıntılı özetlerin pazartesi toplu hazırlanmasına ayrılan süre (dakika);
# yetişmeyenler bot tuşa basılınca anlık üretir
DETAY_SURE_DK = 20

# ---------------------------------------------------------------------------
# 5) 📰 GÜNDEM (haber modülü — her perşembe, gundem.py)
#    Bölümler Telegram'da ayrı tuşlar olarak görünür. Kaynak türleri:
#      rss     : RSS akışı (son GUNDEM_PENCERE_GUN gün)
#      sayfa   : haber sayfası; bağlantıları önceki haftayla karşılaştırılır,
#                yalnızca YENİ çıkanlar alınır (desen: bağlantıda aranan ifade)
#      haber   : Google Haberler araması (dil: "en" ya da "tr")
#      openfda : FDA 510(k) kararları (danışma kurulu kodları)
#    Hepsi Gemini'nin genel cerrahi süzgecinden geçer.
# ---------------------------------------------------------------------------
GUNDEM_BOLUMLERI = {
    "kilavuz": {"ad": "📘 Kılavuz & Kongre", "en_fazla": 8},
    "teknoloji": {"ad": "🤖 Teknoloji & Onaylar", "en_fazla": 8},
    "yerli": {"ad": "🇹🇷 Türkiye", "en_fazla": 8},
    "rct": {"ad": "🧪 Yeni RCT'ler", "en_fazla": 10},
}

GUNDEM_KAYNAKLARI = [
    # --- Kılavuz ve kongre takibi ---
    {"bolum": "kilavuz", "ad": "WSES", "tur": "sayfa",
     "url": "https://www.wses.org.uk/news", "desen": "/news/"},
    {"bolum": "kilavuz", "ad": "ESCP", "tur": "sayfa",
     "url": "https://www.escp.eu.com/news", "desen": r"/news/[a-z-]+/\d+-"},
    {"bolum": "kilavuz", "ad": "ASCRS", "tur": "sayfa",
     "url": "https://fascrs.org/Web/Web/About/News/News.aspx?hkey=42b0d20c-5761-4127-8824-e5c4ca208603",
     "desen": "/News-Articles/"},
    {"bolum": "kilavuz", "ad": "EAES", "tur": "rss", "url": "https://eaes.eu/feed/"},
    {"bolum": "kilavuz", "ad": "SAGES", "tur": "rss", "url": "https://www.sages.org/feed/"},
    # Google Haberler uzun VEYA'lı sorgularda tarih sınırını (when:7d) yok
    # sayıp yıllar öncesini getiriyor; kısa sorgular sınıra uyuyor
    {"bolum": "kilavuz", "ad": "Google Haberler", "tur": "haber", "dil": "en",
     "sorgu": "surgical guideline"},
    {"bolum": "kilavuz", "ad": "Google Haberler", "tur": "haber", "dil": "en",
     "sorgu": "surgery guidelines"},
    {"bolum": "kilavuz", "ad": "Google Haberler", "tur": "haber", "dil": "en",
     "sorgu": "surgical society congress"},
    # --- Teknoloji: FDA/CE onayları, robotik, yapay zekâ ---
    {"bolum": "teknoloji", "ad": "FDA 510(k)", "tur": "openfda",
     # SU: Genel ve Plastik Cerrahi, GU: Gastroenteroloji-Üroloji
     "kurullar": ["SU", "GU"]},
    {"bolum": "teknoloji", "ad": "Google Haberler", "tur": "haber", "dil": "en",
     "sorgu": '(surgical OR surgery OR laparoscopic) ("FDA clearance" OR "FDA approval" '
              'OR "FDA clears" OR "FDA approves" OR "CE mark" OR "510(k)" OR "De Novo")'},
    {"bolum": "teknoloji", "ad": "Google Haberler", "tur": "haber", "dil": "en",
     "sorgu": '("surgical robot" OR "robotic surgical system" OR "surgical robotics" '
              'OR "artificial intelligence surgery" OR "AI surgical")'},
    # --- Yerli gelişmeler ---
    {"bolum": "yerli", "ad": "Türk Cerrahi Derneği", "tur": "sayfa",
     "url": "https://www.turkcer.org.tr/", "desen": "/haber/"},
    {"bolum": "yerli", "ad": "Google Haberler", "tur": "haber", "dil": "tr",
     "sorgu": '("Türk Cerrahi Derneği" OR "Ulusal Cerrahi Kongresi" OR "genel cerrahi" '
              'OR "cerrahi kongresi")'},
    {"bolum": "yerli", "ad": "Google Haberler", "tur": "haber", "dil": "tr",
     # Cerrahiyle ilgili olanları Gemini seçer (dar sorgu hiç sonuç vermiyor)
     "sorgu": '"Türk Tabipleri Birliği"'},
]

# Yeni RCT'ler: ClinicalTrials.gov'a son GUNDEM_PENCERE_GUN günde kaydedilen
# randomize girişimsel çalışmalardan bu terimlerden birini içerenler
RCT_TERIMLERI = [
    "colectomy", "colorectal surgery", "rectal cancer", "colon cancer",
    "hernia", "cholecystectomy", "appendicitis", "appendectomy",
    "pancreatectomy", "pancreatoduodenectomy", "hepatectomy",
    "liver resection", "gastrectomy", "esophagectomy", "bariatric",
    "sleeve gastrectomy", "gastric bypass", "mastectomy", "breast surgery",
    "anastomotic leak", "surgical site infection", "laparoscopic surgery",
    "robotic surgery", "abdominal surgery", "hemorrhoid", "pilonidal",
    "anal fistula", "stoma", "liver transplantation",
    "kidney transplantation", "peritoneal metastases", "HIPEC",
    "emergency laparotomy", "thyroidectomy", "parathyroidectomy", "ERAS",
]

# Başlığında bunlar geçen adaylar Gemini'ye gitmeden elenir (DIGER_BRANSLAR
# ile birlikte). "ASCRS" aynı zamanda bir göz cerrahisi derneğinin kısaltması.
GUNDEM_DISLANAN = DIGER_BRANSLAR + [
    "cardiac", "heart", "cardio*", "valve", "Mohs", "dermatolog*",
    "skin cancer", "cosmetic", "aesthetic", "ophthalm*", "eye", "EyeWorld",
    "refractive", "glaucoma", "orthop*", "veterinar*", "pediatric urolog*",
    "kalp", "kardiyak", "kardiyolo*", "diş", "göz", "estetik", "ortopedi*",
    "kadın doğum", "jinekolo*", "üroloji*",
]
# Aynı olayı anlatan haberleri birleştirme eşiği: iki başlığın anlamlı
# kelime köklerinin en az bu oranı ortaksa (kısa başlığa göre) aynı haber
BENZERLIK_ESIGI = 0.5
# Gösterilen kısa özetin üst sınırı (karakter)
GUNDEM_OZET_SINIRI = 260

GUNDEM_PENCERE_GUN = 7
# Yapay zekâya bölüm başına gönderilen en fazla aday
GUNDEM_ADAY_SINIRI = 60
# Gündem isteği başına aday (60 aday → 3 istek; ücretsiz yedeklerin sınırına sığar)
GUNDEM_PARTI = 20
