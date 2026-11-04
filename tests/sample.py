# Jira'nın Türkçe CSV export biçimini taklit eden küçük örnek (gerçek veri değil).
HEADER = [
    "Özet", "Talep anahtarı", "Talep Tipi", "Durum", "Atanan", "Raporlayan", "Oluşturma", "Çözme",
    "Customer Request Type", "Özel alan (Deployment Kritik Acil Nedeni)", "Özel alan (Deployment Tarihi)",
    "Özel alan (Deployment Öncesi Test Yapılabilir?)", "Özel alan (Deployment sonrası test yapılabilir?)",
    "Özel alan (Microservisler)", "Özel alan (Microservisler)", "Özel alan (Reporter Department)",
    "Özel alan (Web uygulaması)", "Özel alan (Veri Tabanında Yapısal Bir Değişiklik Yapılıyor mu?)",
]
ROWS = [
    ["Kubernetes Deployment", "SAY-1", "Deployment Talebi", "Kapalı", "uygulayan.a", "talep.a",
     "08.10.2026 10:00", "08.10.2026 21:00", "Kubernetes Deployment", "", "08.10.2026 19:00", "Evet", "Evet",
     "svc-a (ITYE-1)", "svc-b (ITYE-2)", "YAZILIM", "UygA (ITYE-10)", "Hayır"],
    ["Acil düzeltme", "SAY-2", "Deployment Talebi", "Kullanıcı Onayına Gönder", "uygulayan.b", "talep.b",
     "13.10.2026 11:30", "", "IIS Deployment", "Çağrı alımı durdu", "13.10.2026 11:00", "Hayır", "Evet",
     "svc-a (ITYE-1)", "", "", "UygB (ITYE-11)", "Evet"],
]


def csv_bytes() -> bytes:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEADER)
    w.writerows(ROWS)
    return buf.getvalue().encode("utf-8")
