# vDeploy

Jira'daki deployment taleplerini toplayan, dashboard'da görselleştiren ve haftalık rapor üreten küçük bir web uygulaması.

- **Veri girişi:** Jira CSV export yükleme, Jira Data Center REST API ile senkron (PAT), elle talep girişi
- **Dashboard:** haftalık trend, bakım penceresi uyumu, gün × saat yoğunluğu, uygulama / mikroservis / departman / uygulayan kırılımları, planlama süresi dağılımı, dikkat çeken talepler
- **Haftalık rapor:** ekranda görüntüleme, HTML / PDF / Excel (CSV) olarak indirme, SMTP ile e-posta (opsiyonel, zamanlanabilir)
- **Ayarlar ekranı:** SMTP, Jira, bakım penceresi, zamanlama, Active Directory (LDAP) girişi (varsayılan kapalı)

## macOS'ta çalıştırma

Gerekenler: Python 3.10 veya üstü (`python3 --version`). Yoksa `brew install python@3.12` ile kurun.

```bash
git clone https://github.com/ozguryahsii/vDeploy.git
```

```bash
cd vDeploy
```

```bash
./run.sh
```

Tarayıcıda **http://127.0.0.1:3031** adresini açın. İlk çalıştırmada `.venv` oluşturulur ve bağımlılıklar kurulur. Veriler `data/vdeploy.db` (SQLite) dosyasında tutulur.

İlk adımlar:

1. **Veri Aktarımı** ekranına girin. Jira'da filtreyi açıp *Dışa aktar → CSV (Tüm alanlar)* ile aldığınız dosyayı yükleyin.
2. **Ayarlar → Bakım penceresi** ekranından pencereyi kontrol edin. Varsayılan değer Perşembe 18:00–23:59.
3. **Dashboard** ve **Haftalık Rapor** ekranlarına bakın.

## Jira alan eşlemesi

Alanlar Jira'daki görünen adlarıyla eşlenir. Bu yüzden CSV başlıkları ve REST API aynı tabloyu kullanır, `customfield_xxxxx` numaralarını bilmek gerekmez. Eşleme tablosu `vdeploy/importer.py` içindeki `FIELD_ALIASES` sözlüğünde:

| Uygulama alanı | Jira alanı |
|---|---|
| Talep tipi | Customer Request Type |
| Planlanan deploy | Deployment Tarihi |
| Uygulama | Web uygulaması |
| Mikroservisler | Microservisler (tüm sütunlar) |
| Departman | Reporter Department |
| Acil | Deployment Kritik Acil Nedeni dolu **veya** Deployment Önceliği acil/kritik |
| Test yapılabilir mi | Deployment Öncesi / sonrası Test Yapılabilir? |
| DB yapısal değişiklik | Veri Tabanında Yapısal Bir Değişiklik Yapılıyor mu? |
| Oluşturma / Çözüm | Oluşturma / Çözme |

Jira'da deployment **sonucu** (başarılı / başarısız / geri alındı) için bir alan yok. Sonuç, talep detay ekranından uygulama içinde girilir ve yeniden içe aktarmada korunur.

## Metrik tanımları

- **Pencere dışı:** Planlanan deploy zamanı (yoksa çözüm zamanı) bakım penceresine düşmüyor.
- **Planlama süresi:** Talebin açılmasından planlanan deploy zamanına kadar geçen süre.
- **Geriye dönük kayıt:** Planlanan deploy zamanı, talebin açılışından önce. Yani iş yapıldıktan sonra kayıt açılmış.
- **Çözüm süresi:** Talebin açılmasından Jira'da çözülmesine kadar geçen süre.
- **Değişiklik başarısızlık oranı:** (Başarısız + Geri alındı) / sonucu girilen talepler.
- **Haftaya atama:** Planlanan deploy tarihine göre (yoksa çözüm, o da yoksa oluşturma). Hafta Pazartesi başlar.

## Ortam değişkenleri (opsiyonel)

| Değişken | Varsayılan |
|---|---|
| `VDEPLOY_PORT` | `3031` |
| `VDEPLOY_HOST` | `127.0.0.1` (ağdan erişim için `0.0.0.0`) |
| `VDEPLOY_DATA_DIR` | `./data` |
| `VDEPLOY_DATABASE_URL` | `sqlite:///data/vdeploy.db` |
| `VDEPLOY_TIMEZONE` | `Europe/Istanbul` |
| `VDEPLOY_SCHEDULER` | `1` (haftalık iş zamanlayıcısı) |

## Güvenlik notları

- SMTP parolası ve Jira token'ı veritabanında **düz metin** tutulur. `data/` klasörünün erişimini kısıtlayın.
- AD girişi kapalıyken uygulamaya erişebilen herkes her şeyi görebilir ve değiştirebilir. Varsayılan olarak yalnızca `127.0.0.1` dinlenir.
- Jira export'ları kişi adları içerir. `.gitignore`, `*.csv` ve `data/` dosyalarını repodan dışarıda tutar.

## Geliştirme

```bash
.venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q
```
