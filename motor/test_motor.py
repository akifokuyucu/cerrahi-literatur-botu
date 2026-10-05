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


if __name__ == "__main__":
    unittest.main()
