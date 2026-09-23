https://discord.gg/psq6P3fVvN

# xaloAC

**xaloAC**, `x410m1s0` tarafından geliştirilen, Windows odaklı bir masaüstü dosya komuta merkezidir. Araç; dosyaları tarar, indeksler, sınıflandırır, arar, önizler, hash üretir, arşivleri inceler ve isteğe bağlı olarak dosyaları kategori klasörlerine düzenler.

> xaloAC bir antivirüs, EDR, güvenlik açığı tarayıcısı veya adli bilişim platformu değildir. Güvenilmeyen dosyaları çalıştırmadan veya çıkarmadan önce mutlaka kontrol edin.

## Özellikler

- Masaüstü veya belirtilen kök dizinde hızlı/deep dosya taraması
- Beş dakikalık yerel JSON indeks önbelleği
- Dosya adına veya regex'e göre arama
- Metin ve kod dosyalarında içerik arama
- Uzantı ve kategori bazlı listeleme
- Metin, CSV, PNG, JPEG, PDF ve arşiv önizlemeleri
- SHA-256 varsayılan olmak üzere MD5, SHA-1 ve SHA-512 hash hesaplama
- Aynı boyut ve içerikteki yinelenen dosyaları bulma
- ZIP/APK/JAR arşivlerini yerel olarak listeleme ve çıkarma
- RAR, 7z ve diğer desteklenen arşivlerde 7-Zip entegrasyonu
- CSV veya JSON indeks dışa aktarımı
- Kategori bazlı organize planı; varsayılan olarak dry-run
- Varsayılan uygulamayla dosya açma
- Kontrollü biçimde yerel Python script çalıştırma
- Etkileşimli terminal menüsü

## Gereksinimler

- Windows 10/11
- Python 3.9 veya üzeri
- Windows'ta `py -3` launcher'ı (kurulum betiğinin smoke test'i bunu kullanır)
- RAR/7z/TAR gibi arşivler için isteğe bağlı [7-Zip](https://www.7-zip.org/)

Harici Python paketi gerekmez; uygulama standart kütüphane ile çalışır.

## Kurulum

PowerShell'i proje klasöründe açın:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install-xaloAC.ps1
```

Kurulum betiği proje klasörünü kullanıcı PATH'ine ekler. İşlemden sonra yeni bir terminal açın ve doğrulayın:

```powershell
xaloAC --version
xaloAC --help
```

Launcher kullanmadan doğrudan çalıştırmak da mümkündür:

```powershell
py -3 .\xaloAC.py --version
```

## Hızlı başlangıç

```powershell
# Varsayılan masaüstünü tara
xaloAC scan

# İstatistikleri göster
xaloAC stats

# Belirli bir kökü tara
xaloAC --root "C:\Users\me\Documents" stats

# Dosya adına göre ara
xaloAC find proje

# Regex ile ara
xaloAC find "^rapor-.*\.pdf$" --re

# Metin dosyalarının içinde ara
xaloAC grep password --max 50

# Uzantıya göre listele
xaloAC ls py -n 30

# Dosyayı önizle
xaloAC view .\notlar.txt

# Dosya hash'i hesapla
xaloAC hash .\arsiv.zip --algo sha256
```

## Komutlar

| Komut | Açıklama |
|---|---|
| `scan` | Kök dizini tarar ve indeksi kaydeder. |
| `stats` | Dosya, klasör, kategori, uzantı ve boyut istatistiklerini gösterir. |
| `menu` | Etkileşimli terminal menüsünü açar. |
| `tree` | Klasör ağacını gösterir. |
| `find <sorgu>` | Dosya adı/yolunda düz metin arar; `--re` regex kullanır. |
| `grep <sorgu>` | Metin ve kod dosyalarının içeriğinde arar. |
| `ls <uzantı>` | Uzantıya göre dosya listeler. |
| `view <yol>` | Dosya türüne göre güvenli önizleme gösterir. |
| `open <yol>` | Dosyayı işletim sisteminin varsayılan uygulamasıyla açar. |
| `hash <yollar...>` | Dosyaların hash değerlerini hesaplar. |
| `zip list <yol>` | Arşiv içeriğini listeler. |
| `zip extract <yol>` | Arşivi varsayılan veya `--out` dizinine çıkarır. |
| `dupes` | En az 1 KiB olan yinelenen dosyaları bulur. |
| `export` | İndeksi CSV veya JSON olarak dışa aktarır. |
| `organize` | Kök dizindeki dosyalar için düzenleme planı üretir. |
| `scripts` | İndeksteki Python dosyalarını listeler. |
| `run <yol>` | Belirtilen Python scriptini çalıştırır. |
| `large` / `recent` | En büyük veya en yeni dosyaları listeler. |
| `cats` | Kategori özetini gösterir. |

Her komutun seçeneklerini görmek için:

```powershell
xaloAC <komut> --help
```

## İndeks ve önbellek

İndeks varsayılan olarak kullanıcı profilindeki şu dizinde tutulur:

```text
%USERPROFILE%\tools\xaloAC\.cache\desktop_index.json
```

Önbelleği yok sayıp yeniden taramak için global `--fresh` seçeneğini komuttan önce kullanın:

```powershell
xaloAC --fresh stats
xaloAC --root "C:\Data" --fresh scan
```

İndeks dosya içeriklerini saklamaz; yol, isim, uzantı, boyut, değiştirilme zamanı ve kategori metadatasını saklar.

## Organize işlemi

İlk çalıştırmada yalnızca plan gösterilir:

```powershell
xaloAC organize
```

Dosyaları kopyalamak için:

```powershell
xaloAC organize --apply
```

Dosyaları taşımak için:

```powershell
xaloAC organize --apply --move
```

Çıktı kök dizin altında `_xaloAC_sorted` klasörüne yazılır. `--move` gerçek dosyaları yerinden kaldırdığı için önce dry-run çıktısını inceleyin ve önemli verilerinizin yedeğini alın.

## Güvenlik ve kullanım sınırları

- `run` komutu Python kodunu doğrudan çalıştırır; yalnızca güvendiğiniz scriptleri çalıştırın.
- `open` komutu `.exe`, `.cmd`, `.bat` gibi çalıştırılabilir dosyaları işletim sistemiyle açabilir.
- Güvenilmeyen arşivleri çıkarmayın. Arşiv içeriğini önce `zip list` ile inceleyin.
- `organize --apply --move` geri alma mekanizması olmadan dosya konumlarını değiştirir.
- İçerik araması yaklaşık 8 MB'tan büyük dosyaları ve ikili dosyaları atlar; varsayılan toplam sonuç sınırı 50'dir.
- Tarama sırasında sistem ve ağır klasörlerin bir bölümü bilinçli olarak atlanır.

## Proje yapısı

```text
xaloAC/
├── xaloAC.py              # Ana CLI uygulaması
├── xaloAC.cmd             # Windows launcher
├── install-xaloAC.ps1     # Kullanıcı PATH kurulumu
├── README.md              # Proje dokümantasyonu
├── LICENSE                # Lisans
├── tests/                 # Test alanı
├── data/                  # Veri alanı
└── xaloAC/                # Gelecekte modüler bileşenler için iskelet
```

## Geliştirme

Kod değişikliklerinden sonra en azından şu kontrolleri çalıştırın:

```powershell
py -3 -m py_compile .\xaloAC.py
py -3 .\xaloAC.py --help
py -3 .\xaloAC.py --version
```

Testler eklendiğinde `tests/` altında tutulmalıdır. Yeni özellikler mevcut CLI adlandırmasını, `xaloAC` marka yazımını ve Windows uyumluluğunu korumalıdır.

## Marka

- Ürün adı: **xaloAC**
- Geliştirici / marka sahibi: **x410m1s0**
- Sürüm: **1.0.0**

## Lisans

Bu proje MIT Lisansı ile dağıtılır. Ayrıntılar için [LICENSE](./LICENSE) dosyasına bakın.
