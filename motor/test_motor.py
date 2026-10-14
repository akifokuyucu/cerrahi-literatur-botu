"""
Motor birim testleri (ağa çıkmaz). Çalıştırma:
  cd motor && python -m unittest test_motor -v
"""
import json
import os
import unittest
from unittest import mock

import llm

KISA_SEMA = {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "pmid": {"type": "STRING"}}, "required": ["pmid"]}}


class Yanit:
    def __init__(self, durum, govde, basliklar=None):
        self.status_code, self.ok = durum, 200 <= durum < 300
        self._govde = govde
        self.text = govde if isinstance(govde, str) else json.dumps(govde)
        self.headers = basliklar or {}

    def json(self):
        return self._govde if not isinstance(self._govde, str) else json.loads(self._govde)


def gemini_ok(veri):
    return Yanit(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(veri)}]}}]})


def openai_ok(metin):
    return Yanit(200, {"choices": [{"message": {"content": metin}}]})


def zincir(*tanimlar, **kw):
    ortam = {"GEMINI_API_KEY": "g", "GROQ_API_KEY": "q", "CEREBRAS_API_KEY": "c",
             "OLLAMA_URL": "http://localhost:11434"}
    with mock.patch.dict(os.environ, ortam, clear=True):
        return llm.Zincir([llm.saglayici_kur(t) for t in tanimlar], **kw)


class ZincirTesti(unittest.TestCase):
    def setUp(self):
        self.uyku = mock.patch("llm.time.sleep").start()
        self.addCleanup(mock.patch.stopall)

    def calistir(self, z, yanitlar, metin="soru", sema=KISA_SEMA):
        giden = []

        def post(url, json=None, **kw):
            giden.append((url, json))
            return yanitlar.pop(0)
        with mock.patch("llm.requests.post", side_effect=post):
            return z.uret(metin, sema=sema), giden

    def test_ilk_saglayici_yanit_verirse_o_kullanilir(self):
        z = zincir("gemini:a", "groq:b")
        veri, giden = self.calistir(z, [gemini_ok([{"pmid": "1"}])])
        self.assertEqual(veri, [{"pmid": "1"}])
        self.assertEqual(len(giden), 1)
        self.assertEqual(z.son_model, "a")

    def test_yogunsa_baska_saglayiciya_gecer(self):
        z = zincir("gemini:a", "groq:llama", yogun_deneme=2)
        veri, giden = self.calistir(z, [
            Yanit(503, "overloaded"), Yanit(503, "overloaded"),
            openai_ok('```json\n{"sonuc": [{"pmid": "7"}]}\n```')])
        self.assertEqual(veri, [{"pmid": "7"}])  # {"sonuc": [...]} açıldı
        self.assertIn("api.groq.com", giden[2][0])
        self.assertEqual(giden[2][1]["response_format"], {"type": "json_object"})
        self.assertEqual(z.son_model, "groq/llama")
        self.assertEqual(z.kullanim, {"groq/llama": 1})
        self.assertIn("a: yoğun", z.notlar)

    def test_gunluk_kota_dolan_bir_daha_denenmez(self):
        z = zincir("gemini:a", "gemini:b")
        self.calistir(z, [Yanit(429, "Quota exceeded ... PerDay"), gemini_ok([{"pmid": "1"}])])
        _, giden = self.calistir(z, [gemini_ok([{"pmid": "2"}])])
        self.assertIn("/b:generateContent", giden[0][0])

    def test_dakika_kotasinda_bekleyip_ayni_saglayiciyi_dener(self):
        z = zincir("gemini:a", "gemini:b")
        _, giden = self.calistir(z, [Yanit(429, "rate", {"retry-after": "5"}),
                                     gemini_ok([{"pmid": "1"}])])
        self.assertTrue(all("/a:" in u for u, _ in giden))
        self.uyku.assert_called_with(6)

    def test_semaya_uymayan_yanit_reddedilir(self):
        z = zincir("gemini:a", "gemini:b")
        veri, _ = self.calistir(z, [gemini_ok({"yanlis": 1}), gemini_ok([{"pmid": "3"}])])
        self.assertEqual(veri, [{"pmid": "3"}])
        self.assertEqual(z.son_model, "b")

    def test_uzun_metin_kucuk_sinirli_saglayiciya_gitmez(self):
        z = zincir("cerebras:gpt-oss-120b", "gemini:a")
        _, giden = self.calistir(z, [gemini_ok([{"pmid": "1"}])], metin="x" * 30000)
        self.assertIn("generativelanguage", giden[0][0])

    def test_json_modu_desteklenmezse_talimatla_dener(self):
        z = zincir("groq:b")
        veri, giden = self.calistir(z, [
            Yanit(400, "response_format is not supported"),
            openai_ok('Elbette: {"sonuc": [{"pmid": "4"}]}')])
        self.assertEqual(veri, [{"pmid": "4"}])
        self.assertNotIn("response_format", giden[1][1])
        self.assertEqual(giden[1][1]["messages"][0]["content"].count("Yanıtı YALNIZCA"), 1)

    def test_ollama_semayi_format_olarak_alir(self):
        z = zincir("ollama:gemma3:4b")
        veri, giden = self.calistir(z, [Yanit(200, {"message": {"content": '[{"pmid": "5"}]'}})])
        self.assertEqual(veri, [{"pmid": "5"}])
        self.assertEqual(giden[0][1]["model"], "gemma3:4b")
        self.assertEqual(giden[0][1]["format"]["type"], "array")
        self.assertEqual(giden[0][1]["format"]["items"]["type"], "object")

    def test_kaldirilan_model_bir_daha_denenmez(self):
        z = zincir("gemini:eski", "gemini:yeni")
        self.calistir(z, [Yanit(404, "models/eski is not found"), gemini_ok([{"pmid": "1"}])])
        _, giden = self.calistir(z, [gemini_ok([{"pmid": "2"}])])
        self.assertEqual(len(giden), 1)
        self.assertIn("/yeni:generateContent", giden[0][0])
        self.assertIn("eski: erişilemiyor", z.notlar)

    def test_json_olmayan_yanit_beklemeden_gecer(self):
        # Kapanan bir servis 200 + düz metin "OK" döndürebiliyor (GitHub Models)
        z = zincir("groq:b", "gemini:a", yogun_deneme=3)
        veri, giden = self.calistir(z, [Yanit(200, "OK"), gemini_ok([{"pmid": "1"}])])
        self.assertEqual(veri, [{"pmid": "1"}])
        self.assertEqual(len(giden), 2)
        self.uyku.assert_not_called()

    def test_hepsi_basarisizsa_hata(self):
        z = zincir("gemini:a", yogun_deneme=1)
        with self.assertRaises(RuntimeError):
            self.calistir(z, [Yanit(503, "x")])

    def test_anahtarsiz_saglayici_zincire_girmez(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "g"}, clear=True):
            z = llm.Zincir()
        self.assertTrue(all(isinstance(s, llm.GeminiSaglayici) for s in z.saglayicilar))
        self.assertEqual(z.model, "gemini-flash-latest")

    def test_zincir_degiskenle_degistirilebilir(self):
        ortam = {"GEMINI_API_KEY": "g", "OLLAMA_URL": "http://x",
                 "LLM_ZINCIRI": "ollama:qwen3:8b, gemini:z"}
        with mock.patch.dict(os.environ, ortam, clear=True):
            z = llm.Zincir()
        self.assertEqual([s.ad for s in z.saglayicilar], ["ollama/qwen3:8b", "z"])


class DetayTesti(unittest.TestCase):
    def setUp(self):
        mock.patch("detay.time.sleep").start()
        self.addCleanup(mock.patch.stopall)

    def test_jats_kaynakca_ve_tablolari_atar(self):
        import detay
        xml = ("<article><front>X</front><body><sec><title>Methods</title>"
               "<p>Hasta &amp; yöntem <xref>[1]</xref>.</p><table-wrap>T</table-wrap>"
               "</sec><ref-list>KAYNAK</ref-list></body></article>")
        metin = detay.jats_metne(xml)
        self.assertIn("## Methods", metin)
        self.assertIn("Hasta & yöntem", metin)
        self.assertNotIn("KAYNAK", metin)
        self.assertNotIn("T\n", metin)

    def test_onceki_ozet_yeniden_uretilmez(self):
        import detay
        z = mock.Mock(son_model="m")
        z.uret.return_value = {"tek_cumle": "yeni"}
        makaleler = [{"pmid": "1", "dergi": "D", "baslik": "B"},
                     {"pmid": "2", "dergi": "D", "baslik": "B"}]
        sonuc = detay.hepsini_hazirla(z, makaleler, {"1": {"d": "eski"}}, 5,
                                      tam_metin_al=False)
        self.assertEqual(sonuc["1"], {"d": "eski"})
        self.assertEqual(sonuc["2"]["d"], {"tek_cumle": "yeni"})
        self.assertEqual(z.uret.call_count, 1)

    def test_art_arda_hatada_durur(self):
        import detay
        z = mock.Mock(son_model="m")
        z.uret.side_effect = RuntimeError("hiçbiri yanıt vermedi")
        makaleler = [{"pmid": str(i), "dergi": "D", "baslik": "B"} for i in range(5)]
        self.assertEqual(detay.hepsini_hazirla(z, makaleler, {}, 5, tam_metin_al=False), {})
        self.assertEqual(z.uret.call_count, 4)

    def test_sure_dolunca_kalanlar_birakilir(self):
        import detay
        z = mock.Mock(son_model="m")
        z.uret.return_value = {}
        makaleler = [{"pmid": str(i), "dergi": "D", "baslik": "B"} for i in range(3)]
        self.assertEqual(detay.hepsini_hazirla(z, makaleler, {}, 0, tam_metin_al=False), {})


class SayiDenetimiTesti(unittest.TestCase):
    KAYNAK = ("In this RCT of 1,250 patients, leak rate was 4.8% vs 13.50% "
              "(RR 0.35; 95% CI 0.12-0.98; P = .047). Median follow-up 24 months.")

    def test_bicim_farklari_kabul_edilir(self):
        import denetim
        ozet = ("1.250 hastalık RCT'de kaçak %4,8'e karşı %13,5 (RR 0,35; %95 CI "
                "0,12-0,98; p=0,047); 24 ay izlem, 3 kol.")
        self.assertEqual(denetim.dogrulanamayan(ozet, self.KAYNAK), [])

    def test_binlik_ayiricisiz_yazim(self):
        import denetim
        self.assertEqual(denetim.dogrulanamayan("1250 hasta", self.KAYNAK), [])

    def test_uydurma_sayilar_bulunur(self):
        import denetim
        ozet = "HR 0,72 bulundu; %13,5 ve 1.300 hasta; NNT 12."
        self.assertEqual(denetim.dogrulanamayan(ozet, self.KAYNAK), ["0,72", "1.300", "12"])

    def test_yaziyla_sayilar_ve_bosluklu_binlik(self):
        import denetim
        kaynak = "Thirty-six patients and Seventeen studies; cost €53 562 vs ninety."
        self.assertEqual(denetim.dogrulanamayan("36 hasta, 17 çalışma, 53562 €, 90", kaynak), [])

    def test_guven_araligi_kalibi_denetlenmez(self):
        import denetim
        ozet = "%95 CI belirtilmemiş; 95% CI ve %95 güven aralığı da yok. Ama %95 başarı."
        self.assertEqual(denetim.dogrulanamayan(ozet, "no numbers here"), ["95"])

    def test_ic_ice_metinler(self):
        import denetim
        self.assertIn("b\nc", denetim.metinler({"a": "b", "x": ["c", {"y": 1}]}))

    def test_kisa_ozet_hatalisi_yeniden_uretilir(self):
        import ozetleyici
        m = {"pmid": "1", "dergi": "D", "baslik": "T", "ozet": "OR 0.5 in 300 patients"}
        z = mock.Mock()
        z.uret.side_effect = [
            [{"pmid": "1", "baslik_tr": "T", "kisa_ozet": "300 hasta, OR 0,7", "cerrahi_ilgi": 2}],
            [{"pmid": "1", "baslik_tr": "T", "kisa_ozet": "300 hasta, OR 0,5", "cerrahi_ilgi": 2}],
        ]
        sonuc = ozetleyici.kisa_ozetle(z, [m])
        self.assertEqual(sonuc["1"]["kisa_ozet"], "300 hasta, OR 0,5")
        self.assertNotIn("sayi_uyarisi", sonuc["1"])
        self.assertIn("0,7", z.uret.call_args_list[1].args[0])  # uyarı notu gitti

    def test_duzelmezse_uyari_isaretlenir(self):
        import ozetleyici
        m = {"pmid": "1", "dergi": "D", "baslik": "T", "ozet": "OR 0.5"}
        hatali = [{"pmid": "1", "baslik_tr": "T", "kisa_ozet": "OR 0,7", "cerrahi_ilgi": 2}]
        z = mock.Mock()
        z.uret.side_effect = [hatali, hatali]
        self.assertEqual(ozetleyici.kisa_ozetle(z, [m])["1"]["sayi_uyarisi"], ["0,7"])


class PartiTesti(unittest.TestCase):
    @staticmethod
    def makaleler(n):
        return [{"pmid": str(i), "dergi": "D", "baslik": "T", "ozet": "x"} for i in range(n)]

    @staticmethod
    def yanitla(metin, sema=None):
        # İstekteki her pmid için özet döndürür
        return [{"pmid": s[6:], "baslik_tr": "T", "kisa_ozet": "ö", "cerrahi_ilgi": 2}
                for s in metin.splitlines() if s.startswith("pmid: ")]

    def setUp(self):
        mock.patch("ozetleyici.time.sleep").start()
        self.addCleanup(mock.patch.stopall)

    def test_esit_partiler(self):
        import ozetleyici
        z = mock.Mock()
        z.uret.side_effect = self.yanitla
        sonuc = ozetleyici.kisa_ozetle(z, self.makaleler(13), parti=7)
        self.assertEqual(len(sonuc), 13)
        boylar = [c.args[0].count("pmid: ") for c in z.uret.call_args_list]
        self.assertEqual(boylar, [7, 6])

    def test_bir_parti_bozulsa_digeri_kalir_ve_eksikler_tekrar_istenir(self):
        import ozetleyici
        z = mock.Mock()
        cagri = {"n": 0}

        def uret(metin, sema=None):
            cagri["n"] += 1
            if cagri["n"] == 1:
                raise RuntimeError("bozuk")
            return self.yanitla(metin)
        z.uret.side_effect = uret
        sonuc = ozetleyici.kisa_ozetle(z, self.makaleler(10), parti=5)
        self.assertEqual(len(sonuc), 10)  # 2. parti + eksiklerin tekrarı
        self.assertEqual(z.uret.call_count, 3)

    def test_uydurma_pmid_alinmaz(self):
        import ozetleyici
        z = mock.Mock()
        z.uret.return_value = [{"pmid": "999", "baslik_tr": "T", "kisa_ozet": "ö", "cerrahi_ilgi": 2},
                               {"pmid": 0, "baslik_tr": "T", "kisa_ozet": "ö", "cerrahi_ilgi": 2}]
        sonuc = ozetleyici.kisa_ozetle(z, self.makaleler(1))
        self.assertEqual(list(sonuc), ["0"])

    def test_hepsi_bozuksa_hata(self):
        import ozetleyici
        z = mock.Mock()
        z.uret.side_effect = RuntimeError("bozuk")
        with self.assertRaises(RuntimeError):
            ozetleyici.kisa_ozetle(z, self.makaleler(3))


class GundemPartiTesti(unittest.TestCase):
    def test_adaylar_partilerle_suzulur(self):
        import gundem
        import ozetleyici
        adaylar = [gundem._aday("teknoloji", "K", f"Başlık {i} robotik sistem onayı {i * 7}",
                                f"https://ornek.com/{i}", "2026-10-01", "metin")
                   for i in range(45)]
        z = ozetleyici.SahteGemini()
        with mock.patch.object(z, "uret", wraps=z.uret) as uret:
            ogeler = gundem.suz(z, "teknoloji", adaylar, bekleme=0)
        self.assertEqual(uret.call_count, 3)  # 20 + 20 + 5
        self.assertTrue(ogeler)


class AkisTesti(unittest.TestCase):
    def test_kucuk_bozukluklar_temizlenir(self):
        import gundem
        bozuk = (b"\xef\xbb\xbf\n  <?xml version=\"1.0\"?><rss><channel><item>"
                 b"<title>Hernia & mesh\x0b</title></item></channel></rss>")
        kok = gundem.xml_coz(bozuk)
        self.assertEqual(kok.find(".//title").text, "Hernia & mesh")

    def test_html_sayfasi_anlasilir_hata(self):
        import gundem
        with self.assertRaisesRegex(ValueError, "HTML"):
            gundem.xml_coz(b"<!DOCTYPE html><html><head><title>Just a moment...</title>"
                           b"<meta charset=utf-8></head></html>")

    def test_akis_okunamazsa_google_haberler_yedegi(self):
        import gundem
        kaynak = {"bolum": "kilavuz", "ad": "EAES", "tur": "rss", "url": "u",
                  "yedek_sorgu": "site:eaes.eu"}
        hatalar = []
        yedek = [gundem._aday("kilavuz", "EAES", "RISE-UK 2026 course", "https://eaes.eu/x")]
        with mock.patch.object(gundem.config, "GUNDEM_KAYNAKLARI", [kaynak]), \
                mock.patch.dict(gundem.OKUYUCULAR, {"rss": mock.Mock(side_effect=ValueError("bot"))}), \
                mock.patch.object(gundem, "haber_oku", return_value=yedek) as haber, \
                mock.patch("traceback.print_exc"):
            adaylar = gundem.adaylari_topla(["kilavuz"], {"ogeler": [], "sayfa": {}}, hatalar)
        self.assertEqual(haber.call_args.args[0]["sorgu"], "site:eaes.eu")
        self.assertEqual(len(adaylar["kilavuz"]), 1)
        self.assertEqual(hatalar, [])


class YokTezTesti(unittest.TestCase):
    SAYFA = """
    <div class="result-card" data-index="0"
         data-kayitno="AAA" data-tezno="BBB">
        <div class="card-title">
           Pilonidal sinüste Limberg flep
        </div>
        <div class="card-info" style="font-style: italic">
           Limberg flap in pilonidal sinus
        </div>
        <div class="card-info" style="white-space: nowrap;"><strong>Tez No:</strong> 1000961</div>
    </div>
    <script>
    referenceData = {
        "0": {
                "meta": {
                    "author": "AD SOYAD", "year": "2026", "subject": "Genel Cerrahi",
                    "type": "Tıpta Uzmanlık", "lang": "Türkçe",
                    "yer": "DÜZCE ÜNİVERSİTESİ / ", "title": "Pilonidal sinüste Limberg flep"
                }
            }
    };
    </script>"""

    def setUp(self):
        import tempfile
        import yoktez
        self.gecici = tempfile.mkdtemp()
        mock.patch.object(yoktez, "GOSTERILEN", os.path.join(self.gecici, "g.json")).start()
        mock.patch.object(yoktez, "CIKTI", self.gecici).start()
        self.addCleanup(mock.patch.stopall)

    def test_sonuc_sayfasi_ayristirilir(self):
        import yoktez
        t = yoktez.sonuclari_ayristir(self.SAYFA)[0]
        self.assertEqual((t["kayit"], t["anahtar"], t["no"]), ("AAA", "BBB", 1000961))
        self.assertEqual(t["baslik_en"], "Limberg flap in pilonidal sinus")
        self.assertEqual((t["konu"], t["tur"], t["yil"], t["universite"]),
                         ("Genel Cerrahi", "Tıpta Uzmanlık", "2026", "DÜZCE ÜNİVERSİTESİ"))

    @staticmethod
    def tez(no, konu="Genel Cerrahi", tur="Tıpta Uzmanlık", yil="2026"):
        return {"kayit": f"k{no}", "anahtar": f"a{no}", "no": no, "baslik": f"Tez {no}",
                "baslik_en": "", "yazar": "Y", "yil": yil, "konu": konu, "tur": tur,
                "universite": "U"}

    def test_secim_kurallari(self):
        import datetime as dt
        import yoktez
        yt = mock.Mock()
        yt.ara.return_value = [
            self.tez(9, konu="Çocuk Cerrahisi"),                 # başka branş
            self.tez(8, konu="Hemşirelik; Genel Cerrahi", tur="Doktora"),  # hemşirelik
            self.tez(7, tur="Yüksek Lisans"),                    # tür dışı
            self.tez(6, yil="2023"),                             # eski
            self.tez(5),                                         # başka alanda seçildi
            self.tez(4),                                         # özeti yok
            self.tez(3),                                         # ✓
            self.tez(2),
        ]
        ozetler = {4: "", 3: "Amaç: " + "x" * 200}
        yt.ayrinti.side_effect = lambda t: {"ozet_tr": ozetler.get(t["no"], "y" * 200), "ozet_en": "",
                                            "danisman": "PROF. DR. D", "kurum": "U / TIP / GENEL CERRAHİ"}
        with mock.patch.dict(yoktez.config.YOKTEZ_TERIMLERI, {"kolorektal": ["a", "b"]}):
            m = yoktez.tez_sec(yt, "kolorektal", haric=[5], bugun=dt.date(2026, 10, 5))
        self.assertEqual((m["pmid"], m["tez_no"], m["dergi"]), ("tez3", 3, "YÖK Tez"))
        self.assertEqual(m["tip_etiketi"], "Tıpta Uzmanlık tezi")
        self.assertTrue(m["ozet"].startswith("Amaç"))

    def test_gosterilen_tez_tekrar_secilmez(self):
        import datetime as dt
        import yoktez
        yt = mock.Mock()
        yt.ara.return_value = [self.tez(3), self.tez(2)]
        yt.ayrinti.return_value = {"ozet_tr": "x" * 200, "ozet_en": "", "danisman": "", "kurum": ""}
        yoktez.gosterildi_isaretle("meme", 3)  # başka alanda daha önce gösterildi
        with mock.patch.dict(yoktez.config.YOKTEZ_TERIMLERI, {"kolorektal": ["a"]}):
            m = yoktez.tez_sec(yt, "kolorektal", bugun=dt.date(2026, 10, 5))
        self.assertEqual(m["tez_no"], 2)


def kayit(pmid, baslik, ozet="Patients were included.", dergi="Surgery", pt=()):
    return {"pmid": pmid, "baslik": baslik, "ozet": ozet, "dergi": dergi,
            "dergi_tam": dergi, "yayin_tipleri": list(pt), "yil": "2026",
            "doi": "", "pmc": ""}


class PuanlamaTesti(unittest.TestCase):
    def test_kilavuz_basligi(self):
        import puanlama
        tip = lambda b: puanlama.calisma_tipi(kayit("1", b))
        self.assertEqual(tip("WSES guidelines on acute appendicitis"), "kilavuz")
        self.assertEqual(tip("Diverticulitis: an international consensus statement"), "kilavuz")
        self.assertNotEqual(tip("Universal versus Guideline-Directed Germline Testing"), "kilavuz")
        self.assertNotEqual(tip("Compliance with the ESMO guidelines in rectal cancer"), "kilavuz")
        self.assertNotEqual(tip("Impact of a Scheduling Guideline on Imaging Times"), "kilavuz")

    def test_dusuk_dergi_eksi_puan(self):
        import puanlama
        self.assertEqual(puanlama.dergi_puani("Cureus", "kolorektal"), (-1, "Düşük"))

    def test_sjr_ceyrekligi(self):
        import puanlama
        tablo = {"11112222": "Q1c", "33334444": "Q4", "55556666": "Q1", "00034932": "Q1c"}
        with mock.patch.object(puanlama, "_SJR", tablo):
            # Listede olmayan dergi ISSN'iyle; birden çok ISSN'de en iyisi
            self.assertEqual(puanlama.dergi_puani("X", "kolorektal", ["33334444", "11112222"]),
                             (1, "SJR Q1 cerrahi"))
            self.assertEqual(puanlama.dergi_puani("Y", "kolorektal", ["33334444"]), (-1, "SJR Q4"))
            # Cerrahi dışı Q1 artı puan almaz
            self.assertEqual(puanlama.dergi_puani("W", "kolorektal", ["55556666"]), (0, "SJR Q1"))
            self.assertEqual(puanlama.dergi_puani("Z", "kolorektal", ["99990000"]), (0, "Listede yok"))
            # Elle kademelendirilmiş liste önce gelir
            self.assertEqual(puanlama.dergi_puani("Ann Surg", "kolorektal", ["00034932"]),
                             (2, "Kademe 2"))

    def test_sjr_donusturme(self):
        import tempfile
        import sjr
        csv_metni = (
            "Rank;Sourceid;Title;Type;Issn;SJR;SJR Best Quartile;Total Docs. (2025);Categories;Areas\n"
            "1;1;A;journal;\"00034932, 15281140\";5,1;Q1;100;Surgery (Q1);Medicine\n"
            "2;2;B;journal;\"12345678\";0,4;Q1;100;\"Surgery (Q3); History (Q1)\";\"Medicine; Arts\"\n"
            "3;3;C;journal;\"87654321\";0,4;Q1;100;Physics (Q1);Physics\n"
            "4;4;D;book series;\"11223344\";0,4;Q1;100;Surgery (Q1);Medicine\n"
            "5;5;Spine J;journal;\"55556666\";0,4;Q1;100;\"Orthopedics and Sports Medicine (Q1); Surgery (Q1)\";Medicine\n"
            "6;6;Aesthetic Plastic Surgery;journal;\"77778888\";0,4;Q1;100;Surgery (Q1);Medicine\n")
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "s.csv")
            with open(yol, "w", encoding="utf-8") as f:
                f.write(csv_metni)
            veri = sjr.donustur(yol)
        self.assertEqual(veri["yil"], "2025")
        # B: en iyi çeyreklik Q1 ama Surgery kategorisindeki Q3 esas alınır;
        # ortopedi/plastik cerrahi dergileri genel cerrahi ("c") sayılmaz
        self.assertEqual(veri["dergiler"], {"00034932": "Q1c", "15281140": "Q1c",
                                            "12345678": "Q3c", "55556666": "Q1",
                                            "77778888": "Q1"})

    def test_haric_terim_alana_girmez(self):
        import puanlama
        disk = kayit("1", "Ozone therapy for lumbar disc herniation")
        fitik = kayit("2", "Mesh repair of inguinal hernia")
        _, tum = puanlama.ilk_n([disk, fitik], "herni")
        self.assertEqual([m["pmid"] for m in tum], ["2"])

    def test_makale_en_uygun_alanda_kalir(self):
        import puanlama
        m = kayit("1", "Robotic esophagectomy for esophageal cancer",
                  "Robotic surgery and laparoscopic approaches were compared.")
        diger = kayit("2", "Robotic surgery for colorectal cancer")
        dagitim = puanlama.alanlara_dagit({
            "mis": [puanlama.puanla(m, "mis"), puanlama.puanla(diger, "mis")],
            "ust_gis": [puanlama.puanla(m, "ust_gis")]})
        self.assertEqual([x["pmid"] for x in dagitim["ust_gis"]], ["1"])
        self.assertEqual([x["pmid"] for x in dagitim["mis"]], ["2"])

    def test_yapay_zeka_suzer_ve_siralar(self):
        import puanlama
        adaylar = [puanlama.puanla(kayit(str(i), f"Study {i}"), "kolorektal")
                   for i in range(4)]
        yz = {"0": {"cerrahi_ilgi": 2, "alan_uyumu": 0, "pratik_etkisi": 2},  # alan dışı
              "1": {"cerrahi_ilgi": 2, "alan_uyumu": 1, "pratik_etkisi": 0},
              "2": {"cerrahi_ilgi": 2, "alan_uyumu": 2, "pratik_etkisi": 2},
              "3": {"cerrahi_ilgi": "bozuk"}}  # bozuk değer nötr sayılır
        secim = puanlama.yz_ile_sec(adaylar, yz)
        self.assertEqual([m["pmid"] for m in secim], ["2", "3", "1"])
        self.assertEqual([m["yz_puani"] for m in secim], [2, 0, -1])


class PubmedSinyalTesti(unittest.TestCase):
    XML = """<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>9</PMID>
    <Article><Journal><ISSN IssnType="Electronic">2168-6254</ISSN><Title>J</Title><JournalIssue><PubDate><Year>2026</Year></PubDate></JournalIssue></Journal>
    <ArticleTitle>T</ArticleTitle><Abstract><AbstractText>Trial NCT11112222.</AbstractText></Abstract>
    <DataBankList><DataBank><DataBankName>ClinicalTrials.gov</DataBankName>
    <AccessionNumberList><AccessionNumber>NCT04306458</AccessionNumber></AccessionNumberList></DataBank></DataBankList>
    </Article><MedlineJournalInfo><MedlineTA>JAMA Surg</MedlineTA></MedlineJournalInfo>
    <CommentsCorrectionsList><CommentsCorrections RefType="CommentIn"><RefSource>x</RefSource></CommentsCorrections>
    <CommentsCorrections RefType="ErratumIn"><RefSource>y</RefSource></CommentsCorrections></CommentsCorrectionsList>
    <MeshHeadingList><MeshHeading><DescriptorName>Humans</DescriptorName></MeshHeading>
    <MeshHeading><DescriptorName>Hernia, Ventral</DescriptorName></MeshHeading></MeshHeadingList>
    </MedlineCitation></PubmedArticle></PubmedArticleSet>"""

    def test_mesh_editoryal_nct(self):
        import pubmed
        k = pubmed.xml_ayristir(self.XML)[0]
        self.assertEqual(k["mesh"], ["Humans", "Hernia, Ventral"])
        self.assertEqual(k["editoryal"], 1)
        self.assertEqual(k["nct"], "NCT04306458")  # DataBank, özetteki numaradan önce
        self.assertEqual(k["issn"], ["21686254"])

    def test_editoryal_puan_ekler(self):
        import puanlama
        k = kayit("1", "Mesh repair", dergi="Hernia")
        self.assertEqual(puanlama.puanla({**k, "editoryal": 2}, "herni")["toplam"],
                         puanlama.puanla(k, "herni")["toplam"] + 1)

    def test_yalniz_cocuk(self):
        import puanlama
        c = lambda **e: puanlama.yalniz_cocuk({**kayit("1", e.pop("b", "Hernia repair")), **e})
        self.assertTrue(c(mesh=["Humans", "Child"]))
        self.assertFalse(c(mesh=["Humans", "Child", "Adult"], b="Hernia in children"))
        self.assertTrue(c(dergi="J Pediatr Surg"))
        self.assertTrue(c(b="Appendicitis in children"))
        self.assertFalse(c(b="Appendicitis in children and adults"))
        self.assertFalse(c(b="Hepatectomy in Child-Pugh B patients"))
        self.assertIsNone(puanlama.calisma_tipi(kayit("1", "K-wires in pediatric fractures")))

    def test_mesh_hayvan(self):
        import puanlama
        k = {**kayit("1", "Anastomotic healing randomized trial"), "mesh": ["Animals"]}
        self.assertEqual(puanlama.calisma_tipi(k), "diger")


class IlgiTesti(unittest.TestCase):
    def ilgi(self, dergi, tip, acildi, n=1):
        return [{"dergi": dergi, "tip": tip, "g": 1, **({"d": 1} if acildi else {})}] * n

    def test_acilma_orani_ham_sayidan_bagimsiz(self):
        import puanlama
        # Ann Surg çok gösterildi, oranı genel oranla aynı (%50): katkı ~0;
        # Hernia az gösterildi ama hep açıldı: artı; Cureus hiç açılmadı: eksi
        ilgiler = (self.ilgi("Ann Surg", "rct", True, 10) + self.ilgi("Ann Surg", "rct", False, 10)
                   + self.ilgi("Hernia", "rct", True, 4) + self.ilgi("Cureus", "rct", False, 4))
        k = puanlama.ilgi_katkisi(ilgiler)["dergi"]
        self.assertAlmostEqual(k["annsurg"], 0, places=6)
        self.assertGreater(k["hernia"], 0.2)
        self.assertLess(k["cureus"], -0.2)
        self.assertAlmostEqual(k["hernia"], -k["cureus"])

    def test_tek_tiklama_kucuk_katki(self):
        import puanlama
        ilgiler = self.ilgi("A", "rct", False, 9) + self.ilgi("B", "rct", True)
        self.assertLess(puanlama.ilgi_katkisi(ilgiler)["dergi"]["b"], 0.2)

    def test_oy_ve_ilgi_toplanir_sinirlanir(self):
        import puanlama
        oylar = [{"oy": 1, "dergi": "Hernia", "tip": "rct"}] * 3  # 3 × 0,25 → sınır 0,5
        ilgiler = self.ilgi("Hernia", "rct", True, 4) + self.ilgi("Cureus", "diger", False, 4)
        t = puanlama.tercihleri_hesapla(oylar, ilgiler)
        self.assertEqual(t["dergi"]["hernia"], 0.5)
        self.assertLess(t["dergi"]["cureus"], 0)
        self.assertEqual(puanlama.tercihleri_hesapla([], []), {"dergi": {}, "tip": {}})


class DunyaTesti(unittest.TestCase):
    def aday(self, i, baslik, metin="Some text."):
        import gundem
        return gundem._aday("dunya", f"Kaynak {i}", baslik, f"https://ornek.com/{i}",
                            "2026-10-10", metin)

    def test_toplama_gorulen_ve_tekrar_ayiklanir(self):
        import dunya
        a, b = self.aday(1, "China elder care plan"), self.aday(2, "US drug prices")
        tekrar = self.aday(3, "China elder care plan!")  # aynı başlık, farklı bağlantı
        kaynaklar = [{"ad": "A", "tur": "rss"}, {"ad": "B", "tur": "rss"}]
        okuyucu = mock.Mock(side_effect=[[a, tekrar], [b]])
        with mock.patch.object(dunya.config, "DUNYA_KAYNAKLARI", kaynaklar), \
                mock.patch.dict(dunya.OKUYUCULAR, {"rss": okuyucu}):
            sonuc = dunya.adaylari_topla([b["id"]], [])
        self.assertEqual([x["id"] for x in sonuc], [a["id"]])

    def test_suzgec_bolum_onem_ve_bolge(self):
        import dunya
        adaylar = [self.aday(i, f"Distinct headline number {i} about topic {i * 7}") for i in range(5)]
        gem = mock.Mock()
        gem.uret.return_value = [
            {"id": adaylar[0]["id"], "bolum": "toplum", "bolge": "Çin", "onem": 3, "baslik_tr": "Çin yaşlı bakımı", "ozet": "Plan açıklandı."},
            {"id": adaylar[1]["id"], "bolum": "toplum", "bolge": "Mars", "onem": "2", "baslik_tr": "Göç eğilimi değişiyor", "ozet": "Rapor yayımlandı."},
            {"id": adaylar[2]["id"], "bolum": "toplum", "bolge": "ABD", "onem": 1, "baslik_tr": "Küçük ayrıntı", "ozet": "x"},
            {"id": adaylar[3]["id"], "bolum": "diger", "bolge": "ABD", "onem": 3, "baslik_tr": "Spor", "ozet": "x"},
            {"id": "uydurma", "bolum": "toplum", "bolge": "ABD", "onem": 3, "baslik_tr": "Yok", "ozet": "x"}]
        b = dunya.suz(gem, adaylar, bekleme=0)
        self.assertEqual([o["baslik_tr"] for o in b["toplum"]], ["Çin yaşlı bakımı", "Göç eğilimi değişiyor"])
        self.assertEqual(b["toplum"][1]["bolge"], "Diğer")  # geçersiz bölge
        self.assertEqual(sum(len(v) for v in b.values()), 2)

    def test_brifing_kaynaksiz_ana_basligi_almaz(self):
        import dunya
        o = {"id": "x1", "kaynak": "Sixth Tone", "url": "https://s.com/1", "baslik_tr": "Çin planı",
             "ozet": "2030 hedefi.", "onem": 3, "bolge": "Çin", "_kaynak_metni": "Plan targets 2030."}
        gem = mock.Mock()
        gem.uret.return_value = {"giris": "Giriş.", "ana_basliklar": [
            {"baslik": "Uydurma", "aciklama": "x", "idler": ["yok"]},
            {"baslik": "Çin planı", "aciklama": "2030'a kadar 500 merkez.", "idler": ["x1"]}]}
        b = dunya.brifing_yaz(gem, {"toplum": [o]})
        self.assertEqual([ab["baslik"] for ab in b["ana_basliklar"]], ["Çin planı"])
        self.assertEqual(b["ana_basliklar"][0]["kaynaklar"], [{"ad": "Sixth Tone", "url": "https://s.com/1"}])
        self.assertEqual(b["ana_basliklar"][0]["sayi_uyarisi"], ["500"])
        gem.uret.return_value = {"giris": "G", "ana_basliklar": [{"baslik": "U", "aciklama": "x", "idler": ["yok"]}]}
        self.assertIsNone(dunya.brifing_yaz(gem, {"toplum": [o]}))

    def test_telegram_metni_kacis_ve_sinir(self):
        import dunya
        ab = {"baslik": "A<b>", "aciklama": "Uzun cümle. " * 300,
              "kaynaklar": [{"ad": "K&K", "url": "https://k.com/?a=1&b=2"}]}
        cikti = {"hafta": "4–11 Ekim", "hatalar": [], "bolumler": {"toplum": {"ad": "👥 Toplum", "ogeler": [1]}},
                 "brifing": {"giris": "G", "ana_basliklar": [ab, ab, ab]}}
        m = dunya.telegram_metni(cikti)
        self.assertLessEqual(len(m), 4000)
        self.assertIn("A&lt;b&gt;", m)
        self.assertIn('href="https://k.com/?a=1&amp;b=2">K&amp;K</a>', m)
        self.assertEqual(m.count("<b>"), m.count("</b>"))  # HTML etiketi bölünmedi
        self.assertIn("/dunya", m)


class ArsivTesti(unittest.TestCase):
    def test_yaz_oku_sec_olc(self):
        import tempfile
        import arsiv
        k1 = kayit("1", "Hernia mesh trial", dergi="Hernia")
        k2 = kayit("2", "Hernia repair cost", dergi="Cureus")
        with tempfile.TemporaryDirectory() as d:
            yol = arsiv.yaz("2026-10-05", {"herni": [k1, k2]},
                            {"2": {"cerrahi_ilgi": 0, "alan": "herni", "kisa_ozet": "x"}}, d)
            a = arsiv.oku(yol)
        self.assertNotIn("kisa_ozet", a["yz"]["2"])
        secim = arsiv.sec(a)
        self.assertEqual([m["pmid"] for m in secim["herni"]], ["1"])
        altin = {"olmali": {"herni": {"1"}}, "olmamali": {"*": {"2"}}}
        self.assertEqual(arsiv.olc(secim, altin, a)["herni"],
                         {"isabet": 1, "olmali": 1, "hatali": 0})


if __name__ == "__main__":
    unittest.main()
