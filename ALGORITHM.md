# Bot Algoritması

Bu doküman, X-Random-Wikipedia-Bot'un makale seçimi ve paylaşım algoritmasının detaylı açıklamasını içerir.

## Genel Akış

Bot her çalıştırıldığında şu adımları takip eder:

1. **Geçmiş Kontrolü**: Son N gün içinde paylaşılan makaleleri yükle (varsayılan: 60 gün)
2. **Makale Seçimi**: Trend olan veya rastgele bir makale seç
3. **Kalite Filtresi**: Düşük kaliteli makaleleri filtrele
4. **Puanlama ve Seçim**: En iyi adaylar arasından seç
5. **Tweet Formatı**: Tweet'i 280 karakter limitine göre formatla
6. **Paylaşım**: Makaleyi X'te (Twitter) paylaş
7. **Geçmiş Güncelleme**: Paylaşılan makaleyi geçmişe ekle

## 1. Makale Kaynaklarının Seçimi

Bot iki farklı kaynaktan makale seçer:

### 1.1. Trend Makaleler (Birincil Kaynak)

Bot öncelikli olarak trend makaleleri tercih eder:

```python
TREND_POOL_SIZE = 500      # Havuzdan alınacak trend makale sayısı
TREND_SAMPLE_SIZE = 60     # Örneklenecek aday sayısı
TREND_PICK_TOP_K = 15      # En iyi N aday arasından rastgele seçim
```

**Adımlar:**

1. **Wikimedia Pageviews API**: Son 1-3 gün içindeki en çok görüntülenen Türkçe Wikipedia makalelerini al
   - API: `https://wikimedia.org/api/rest_v1/metrics/pageviews/top/tr.wikipedia/all-access/{date}`
   - Havuz boyutu: İlk 500 makale

2. **İlk Filtreleme**: 
   - `:` içeren başlıkları filtrele (namespace sayfaları)
   - İstenmeyen başlıkları filtrele (örn: "Anasayfa")
   - Sayfa görüntüleme sayısını sakla

3. **Örnekleme**: 500 makaleden rastgele 60 tanesini seç

4. **Detay Sorgusu**: Seçilen adaylar için Wikipedia Query API'den detaylı bilgi al:
   - Makale özeti (extract)
   - Küçük resim (thumbnail)
   - Sayfa uzunluğu
   - Sayfa özellikleri (pageprops)
   - Tam URL

### 1.2. Rastgele Makaleler (Yedek Kaynak)

Trend makale bulunamazsa rastgele makale seçimi devreye girer:

```python
RANDOM_SAMPLE_SIZE = 20    # Örneklenecek rastgele sayfa sayısı
DEFAULT_RN_MINSIZE = 8000  # Minimum sayfa boyutu (byte)
```

**Adımlar:**

1. **Wikipedia Random API**: Ana namespace'den (namespace 0) redirect olmayan rastgele sayfalar al
   - API: `action=query&list=random&rnnamespace=0&rnfilterredir=nonredirects`
   - Minimum boyut filtresi: 8000 byte
   - Limit: 20 sayfa

2. **Detay Sorgusu**: Rastgele seçilen sayfalar için tam detayları al

3. **Birkaç Deneme**: Uygun makale bulunana kadar 3 kez dene

### 1.3. Son Çare (Fallback)

Her iki yöntem de başarısız olursa:

- Wikipedia REST API'den rastgele özet al: `https://tr.wikipedia.org/api/rest_v1/page/random/summary`
- Minimum kalite kriterlerini kontrol et
- Geçmişte paylaşılmadıysa kullan

## 2. Kalite Filtreleme

Her aday makale şu kriterlere göre filtrelenir:

### 2.1. Temel Zorunlu Kriterler

Bir makale paylaşılabilmesi için şu koşulları **mutlaka** sağlamalıdır:

```python
MIN_EXTRACT_LEN = 100      # Minimum özet uzunluğu
MIN_PAGE_LEN = 5000        # Minimum sayfa uzunluğu (byte)
```

**Kontroller:**

1. **Başlık Kontrolleri**:
   - Başlık boş olmamalı
   - `:` karakteri içermemeli (namespace sayfası olmamalı)
   - İstenmeyen başlıklar listesinde olmamalı
   - `title_key()` fonksiyonu ile normalize edilmiş hali geçmişte bulunmamalı

2. **Sayfa Özellikleri**:
   - Anlam ayrımı (disambiguation) sayfası olmamalı
   - Tam URL bulunmalı
   - Küçük resim (thumbnail) bulunmalı ⚠️ **Zorunlu**

3. **İçerik Uzunlukları**:
   - Özet (extract) en az 100 karakter olmalı
   - Sayfa uzunluğu en az 5000 byte olmalı

### 2.2. Geçmiş Kontrolü

```python
DEFAULT_HISTORY_DAYS = 60  # Geçmiş tutma süresi
```

Makale son 60 gün içinde paylaşılmamış olmalı:

- **Başlık anahtarı** (`title_key()`): Alfanumerik karakterler küçük harfe çevrilir
- **Sayfa ID** (`pageid`): Benzersiz sayfa kimliği kontrol edilir

### 2.3. Konu Tekrarından Kaçınma

```python
DEFAULT_TOPIC_DAYS = 14    # Konu tekrarını önleme süresi
TOPIC_TOKEN_LIMIT = 12     # Makale başına maksimum token sayısı
```

Son 14 gün içinde benzer konuların tekrar paylaşılmasını azaltmak için:

1. **Token Çıkarma**:
   - Başlık ve özetten anlamlı kelimeler (token) çıkar
   - Stopword'leri filtrele (ve, ile, da, de, bir, bu, the, and, vb.)
   - 3 karakterden kısa kelimeleri filtrele
   - Sayı içeren kelimeleri filtrele
   - Kelimeleri uzunluğa göre sırala, en uzun 12 tanesini al

2. **Token Karşılaştırma**:
   - Aday makalenin token'larını son 14 gündeki makalelerle karşılaştır
   - Token çakışması yoksa öncelik ver
   - Tüm adaylarda çakışma varsa, çakışması olanlar arasından seç

## 3. Puanlama Algoritması

Kaliteyi geçen her makale puanlanır:

```python
def score_article(article):
    score = 0.0
    
    # Küçük resim kontrolü
    if article.get('thumbnail_url'):
        score += 5    # Resim varsa +5
    else:
        score -= 5    # Resim yoksa -5 (zaten filtrelenir)
    
    # Özet uzunluğu
    extract_len = len(article.get('extract', '') or '')
    if extract_len >= 200:      # STRONG_EXTRACT_LEN
        score += 3
    elif extract_len >= 100:    # MIN_EXTRACT_LEN
        score += 1
    
    # Sayfa uzunluğu
    page_len = article.get('length') or 0
    if page_len >= 10000:       # STRONG_PAGE_LEN
        score += 2
    elif page_len >= 5000:      # MIN_PAGE_LEN
        score += 1
    
    # Görüntülenme sayısı (sadece trend makaleler için)
    views = article.get('views') or 0
    if views > 0:
        score += min(3.0, log10(views + 1))  # Maksimum +3
    
    return score
```

**Puanlama Faktörleri:**

1. **Küçük Resim**: +5 puan (yoksa -5, ama zaten filtrelenir)
2. **Özet Kalitesi**:
   - 200+ karakter: +3 puan
   - 100-199 karakter: +1 puan
3. **Sayfa Uzunluğu**:
   - 10000+ byte: +2 puan
   - 5000-9999 byte: +1 puan
4. **Popülerlik** (sadece trend makaleler):
   - Logaritmik ölçek: `min(3, log10(views + 1))`
   - Maksimum +3 puan

## 4. Son Seçim Stratejisi

En iyi adaylar arasından rastgelelik ekleyerek seçim yapılır:

### 4.1. Trend Makaleler İçin

```python
TREND_PICK_TOP_K = 15  # En iyi 15 aday arasından seç
```

1. Tüm uygun adayları puanla
2. Konu token çakışmasına göre grupla:
   - Çakışması olmayanları öncelikle değerlendir
   - Tümü çakışıyorsa hepsini değerlendir
3. Puanı en yüksek 15 makale arasından **rastgele** birini seç
4. Bu yaklaşım hem kaliteyi hem de çeşitliliği korur

### 4.2. Rastgele Makaleler İçin

```python
RANDOM_PICK_TOP_K = 5  # En iyi 5 aday arasından seç
```

- Daha küçük bir havuzdan seçim (5 aday)
- Aynı puanlama ve seçim stratejisi

## 5. Geçmiş Yönetimi

Bot, tekrar paylaşımları önlemek için hafif bir geçmiş dosyası kullanır:

### 5.1. Geçmiş Dosyası

**Konum**: `.bot_state/history.json`

**Format**:
```json
[
  {
    "title": "Makale Başlığı",
    "title_key": "makalebaşlığı",
    "pageid": 123456,
    "url": "https://tr.wikipedia.org/wiki/...",
    "timestamp": "2024-01-15T12:30:45.123456+00:00",
    "topic_tokens": ["makale", "konu", "kelime"]
  }
]
```

### 5.2. Geçmiş Temizleme

Her çalıştırmada:

1. Geçmiş dosyasını yükle
2. `HISTORY_DAYS` (varsayılan: 60 gün) öncesinden eski kayıtları sil
3. Güncel kayıtları indexle:
   - `recent_title_keys`: Başlık anahtarları seti
   - `recent_pageids`: Sayfa ID'leri seti
   - `recent_tokens`: Son `TOPIC_DAYS` içindeki konu token'ları seti

### 5.3. Yeni Kayıt Ekleme

Başarılı paylaşımdan sonra:

1. Makale bilgilerini geçmişe ekle
2. Geçmişi tekrar temizle (eski kayıtları sil)
3. Dosyayı atomik olarak kaydet (`.tmp` dosyası kullanılarak)

## 6. Tweet Formatı

Tweet, 280 karakter limitine uygun şekilde formatlanır:

### 6.1. İdeal Format

```
[Başlık]

[Özet]

[URL]
```

**Örnek**:
```
İstanbul

İstanbul, Türkiye'nin en kalabalık şehri ve ekonomik, kültürel, tarihi merkezidir...

https://tr.wikipedia.org/wiki/İstanbul
```

### 6.2. Uzunluk Aşımı Durumunda

```python
TWITTER_CHAR_LIMIT = 280
TRUNCATION_OVERHEAD = 5  # Yeni satırlar ve üç nokta için
```

**Strateji**:

1. **Tam format kontrol**: Başlık + özet + URL toplamı 280'den azsa, direkt kullan

2. **Özet kısaltma**: 280'i aşıyorsa:
   - URL ve başlık için yer ayır (4 yeni satır karakteri ile)
   - Kalan alanı özete ver
   - Özeti kes ve sonuna `...` ekle

3. **Başlık kısaltma**: Başlık bile URL ile 280'i aşıyorsa:
   - Özeti tamamen çıkar
   - Başlığı kes ve sonuna `...` ekle
   - Sadece başlık ve URL paylaş

### 6.3. Medya Ekleme

- Makale küçük resmi (thumbnail) varsa:
  - Resmi indir (geçici dosyaya)
  - Twitter'a yükle
  - `media_id` al
  - Tweet ile birlikte paylaş
  - Geçici dosyayı sil

- Resim hatası durumunda:
  - Sadece metin paylaş
  - Hata logla ama devam et

## 7. Hata Yönetimi ve Fallback Mekanizmaları

Bot, çeşitli hata senaryolarını yönetir:

### 7.1. Makale Seçim Fallback'leri

```
1. Önce Trend Makaleler Dene
   ↓ başarısız
2. Rastgele Makaleler Dene (3 deneme)
   ↓ başarısız
3. Wikipedia REST API Random Summary
   ↓ başarısız
4. Hata döndür, 60 saniye bekle ve tekrar dene
```

### 7.2. API Hataları

- **Wikimedia API Hataları**: Log'la ve bir sonraki adıma geç
- **Twitter API Hataları**: Detaylı hata bilgisi (status code, request ID, body) logla
- **Network Timeout**: 10 saniye timeout, hata durumunda yeniden dene

### 7.3. Dry-Run Modu

```bash
python bot.py --once --dry-run
```

- Tweet paylaşılmaz
- Sadece önizleme gösterilir
- Opsiyonel olarak geçmişe kaydedilebilir (`DRY_RUN_SAVE_HISTORY=true`)
- Test ve debug için idealdir

## 8. Yapılandırma Parametreleri

Bot davranışı environment variables ile ayarlanabilir:

### 8.1. Temel Parametreler

| Parametre | Varsayılan | Açıklama |
|-----------|-----------|----------|
| `POST_INTERVAL` | 3600 | Paylaşımlar arası süre (saniye) |
| `HISTORY_DAYS` | 60 | Geçmiş tutma süresi (gün) |
| `TOPIC_DAYS` | 14 | Konu tekrarını önleme süresi (gün) |
| `RN_MINSIZE` | 8000 | Rastgele sayfa minimum boyutu (byte) |

### 8.2. İleri Seviye Parametreler

| Parametre | Varsayılan | Açıklama |
|-----------|-----------|----------|
| `TREND_POOL_SIZE` | 500 | Trend makale havuz boyutu |
| `TREND_SAMPLE_SIZE` | 60 | Örneklenecek trend aday sayısı |
| `TREND_PICK_TOP_K` | 15 | Trend için en iyi N aday |
| `TREND_DAYS` | 3 | Kaç gün geriye gidileceği (1-3 arası rastgele) |
| `RANDOM_SAMPLE_SIZE` | 20 | Örneklenecek rastgele sayfa sayısı |
| `RANDOM_PICK_TOP_K` | 5 | Rastgele için en iyi N aday |
| `RANDOM_ATTEMPTS` | 3 | Rastgele seçim deneme sayısı |

## 9. Örnek Çalışma Senaryosu

### Başarılı Bir Çalıştırma Örneği:

1. **Başlatma** (16:00)
   - Geçmiş dosyası yüklendi: 45 kayıt
   - 22 gün öncesinden eski 3 kayıt silindi
   - Kalan 42 kayıt indexlendi

2. **Trend Makale Arama**
   - 2 gün önceki pageviews API çağrıldı
   - 500 trend başlık alındı
   - 60 rastgele örnek seçildi
   - Detaylar query API ile alındı (3 batch, 20'şer grup)
   - 48 makale detaylı bilgi geldi

3. **Filtreleme**
   - 5 makale geçmişte paylaşılmış (elendi)
   - 8 makale küçük resmi yok (elendi)
   - 3 makale çok kısa özet (elendi)
   - 2 makale anlam ayrımı sayfası (elendi)
   - **30 uygun aday kaldı**

4. **Konu Kontrolü**
   - 12 adayın konu token'ı son 14 günde paylaşılmış
   - 18 aday hiç çakışmıyor
   - Çakışmayanlar öncelikle değerlendiriliyor

5. **Puanlama**
   - 18 çakışmayan aday puanlandı
   - Puanlar: 8.2, 11.5, 9.1, 13.2, ... (en yüksek: 13.2)
   - En iyi 15 aday seçildi

6. **Seçim**
   - 15 aday arasından rastgele biri seçildi
   - Seçilen: "Yapay Zeka" (puan: 12.8)

7. **Tweet Formatı**
   - Başlık: "Yapay Zeka"
   - Özet: 156 karakter
   - URL: 38 karakter
   - Toplam: 198 karakter ✓
   - Küçük resim indirildi ve yüklendi

8. **Paylaşım**
   - Tweet başarıyla paylaşıldı
   - Geçmişe eklendi (43 kayıt)
   - Sonraki paylaşım: 17:00 (1 saat sonra)

## 10. Algoritmanın Avantajları

1. **Çeşitlilik**: Hem trend hem rastgele makale desteği
2. **Kalite**: Çok katmanlı filtreleme sistemi
3. **Tekrarsızlık**: Geçmiş tabanlı dedup ve konu kontrolü
4. **Esneklik**: Yapılandırılabilir parametreler
5. **Dayanıklılık**: Çok katmanlı fallback mekanizmaları
6. **Hafiflik**: Veritabanı yok, sadece JSON dosyası
7. **Rastgelelik**: Aynı puanlı makaleler arasında rastgele seçim
8. **Popülerlik Dengesi**: Trend makaleler tercih edilir ama zorunlu değil

## 11. Geliştirilmeye Açık Alanlar

Bu algoritma geliştirilmeye açıktır. Potansiyel iyileştirmeler:

- **Zaman dilimi analizi**: Hangi saatlerde hangi konuların trend olduğu
- **Kategori dengesi**: Farklı kategorilerden dengeli seçim
- **Kullanıcı etkileşimi**: Geçmiş tweet'lerin etkileşimine göre strateji
- **Görsel kalite**: Küçük resim kalitesi analizi
- **Dil kalitesi**: Özet metni dil kalitesi kontrolü
- **İlişkili makaleler**: Zincir halinde ilişkili makaleler paylaşma

---

**Son güncelleme**: 2026-01-19
