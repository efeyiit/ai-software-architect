# AI Software Architect — tam kapsam planı

Kaynak: [source-design.md](source-design.md), bölüm 1–57. Amaç CV/GitHub'da kanıtlanabilir, çalışan tam üründür. Kaynak belgedeki MVP/V1/V2/V3/V4 ayrımı burada teslim kapsamını daraltmaz; hepsi yapılacak iş olarak modellenmiştir. Bu dosya uygulama sonucu değil, iş haritasıdır. Ürün kodu, test kanıtı ve demo henüz yapılmadı.

## Çalışma ilkesi

Bir yeni sohbet = bir doğrulanabilir görev kartı. Karttaki davranış, hedefli test ve ilgili belge aynı sohbette biter. Hazır görevler Orvant `context` ile seçilir; açık mimari kararlar görev başında çözülür. Ana Astra sohbeti proje sorumlusu ve Orvant kaydının tek yazıcısıdır; Luna/Sol görev sohbetleri çalışanlardır. Görevlerin model/effort seçimi başlangıç hipotezidir; maliyet veya başarı garantisi değildir. Astra yalnız proje sorumlusunun esaslı ve çözümsüz mimari kararı için ayrılır. `GIT-001` çalışanı Git işlemleri, kök README ve `.gitignore` için tek yazıcıdır; doğrulanmış her adımın public `efeyiit` reposuna commit edilmesi bu ayrı akışta yapılır.

## Akış

1. Sözleşmeler, veri ve GitHub erişimi.
2. Beş dilde yapı çıkarımı; bağımlılık, kalite, mimari, güvenlik, test ve belge analizi.
3. RAG, kaynaklı sohbet, queue, cache ve rapor API; eşzamanlı UI yüzeyleri.
4. Incremental, PR, issue ve mimari tarihçe.
5. Sınır incelemeleri, Docker/CI, gerçek uçtan uca doğrulama ve CV/GitHub demosu.

Bu sıra önkoşul grafını özetler; farklı dallar hazır olduklarında bağımsız ilerleyebilir. Güven sınırı: repository içeriği talimat değil veri; özel kod ve sırlar yetki alanı dışında görünmez; varsayılan analiz kullanıcı kodu çalıştırmaz. Coverage mevcut artefakt olarak okunur, keşif sayıları ayrı gösterilir.

## Açık mimari kararlar

- **D01 — Parser çerçevesi:** Tree-sitter beş dil için ortak başlangıç; gramer/sürüm ve fallback görev başında kanıtla seçilecek. Durum: öneri; kabul edilmiş kullanıcı kararı değil.
- **D02 — Queue teknolojisi:** Redis destekli Celery varsayımı; iptal, retry ve idempotency prototipte karşılaştırılacak. Durum: öneri; kabul edilmiş kullanıcı kararı değil.
- **D03 — LLM ve embedding sağlayıcısı:** Sağlayıcı arayüzü kurulacak; gizli kod gönderimi, maliyet ve veri saklama koşulları onay öncesi incelenecek. Durum: öneri; kabul edilmiş kullanıcı kararı değil.
- **D04 — OAuth kimlik modeli:** GitHub OAuth ve en az yetki; token saklama/yenileme yöntemi güvenlik incelemesinde kesinleşecek. Durum: öneri; kabul edilmiş kullanıcı kararı değil.
- **D05 — Mimari güven hesabı:** Kural kanıtı ile AI yorumu ayrı; güven kalibrasyonu değerlendirme fixturelarıyla seçilecek. Durum: öneri; kabul edilmiş kullanıcı kararı değil.
- **D06 — Gerçek coverage alma:** Yalnız repository içinde mevcut coverage artefaktı okunacak; kullanıcı kodu çalıştırma için ayrı güven sınırı kararı gerekecek. Durum: öneri; kabul edilmiş kullanıcı kararı değil.
- **D07 — PR ve issue yayın politikası:** Webhook salt analiz başlatır; issue yayınlama açık kullanıcı eylemine bağlı kalır. Durum: öneri; kabul edilmiş kullanıcı kararı değil.

## Tamamlanma ölçütü

Tüm görevler kanıtla tamamlanır; birim/entegrasyon/uçtan uca/eval ve gerçek demo raporları vardır; kaynak bölümlerinin 1–57 kapsaması [COVERAGE.md](COVERAGE.md) ile izlenir. Ürün iddiaları yalnız doğrulanan davranışa dayanır. Takvim ve sürüm etiketi atanmaz.
