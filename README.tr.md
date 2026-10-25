# Vitals

[English](README.md) | **Türkçe**

Terminalde çalışan, hafif ve renkli bir sistem monitörü. Vitals; işlemci, bellek, disk, ağ ve en çok kaynak kullanan süreçleri tek bir canlı panelde gösterir.

![Vitals ekran görüntüsü](assets/screenshot.png)

## Özellikler

- **CPU:** toplam kullanım ve her mantıksal çekirdek için ayrı çubuk
- **Bellek:** kullanılan / toplam miktarla birlikte RAM kullanımı
- **Diskler:** bağlı tüm sürücülerin doluluk oranı
- **Ağ:** anlık yükleme/indirme hızı ve toplam trafik
- **Süreçler:** CPU kullanımına göre sıralanmış en yoğun süreçler
- Renkli çubuklar: %50 altı yeşil, %80 altı sarı, üstü kırmızı
- Terminal boyutuna uyum sağlayan tam ekran düzen
- Windows, Linux ve macOS'ta çalışır

## Kurulum

Python 3.10 veya üzeri gerekir.

```bash
git clone https://github.com/Enes0102/vitals-monitor.git
cd vitals-monitor
pip install -r requirements.txt
```

## Kullanım

```bash
python -m vitals
```

Çıkmak için `Ctrl+C`.

| Seçenek | Açıklama | Varsayılan |
|---|---|---|
| `-i`, `--interval` | Yenileme aralığı (saniye) | `1.0` |
| `-n`, `--top` | Gösterilecek süreç sayısı | `20` |
| `-h`, `--help` | Yardım mesajını gösterir | |

Örnek: 2 saniyede bir yenile ve 10 süreç göster:

```bash
python -m vitals -i 2 -n 10
```

## Proje Yapısı

```
vitals-monitor/
├── vitals/
│   ├── __init__.py
│   ├── __main__.py   # komut satırı giriş noktası
│   ├── stats.py      # psutil ile sistem verilerini toplar
│   └── ui.py         # paneli rich ile çizer
├── assets/
│   └── screenshot.png
├── requirements.txt
└── LICENSE
```

Veri toplama (`stats.py`) ve çizim (`ui.py`) birbirinden ayrıdır; böylece her biri tek başına değiştirilebilir veya başka projelerde kullanılabilir.

## Kullanılan Teknolojiler

- [psutil](https://github.com/giampaolo/psutil): platformlar arası sistem bilgisi
- [rich](https://github.com/Textualize/rich): terminal biçimlendirme ve canlı çizim

## Yol Haritası

- [ ] Klavye kısayoluyla süreçleri belleğe göre sıralama
- [ ] CPU ve ağ geçmişi grafikleri
- [ ] Pil ve sıcaklık panelleri
- [ ] Anlık görüntüyü JSON olarak dışa aktarma

## Lisans

Bu proje [MIT Lisansı](LICENSE) ile lisanslanmıştır.
