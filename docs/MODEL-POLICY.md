# Model ve inceleme kuralları

Ana Astra sohbeti **proje sorumlusu**; Luna/Sol görev sohbetleri **çalışan** olarak adlandırılır. Görev adı `Ariadne | <görev ID> | <Luna/Sol> | <kısa iş>`; bu planlama görevi `Ariadne | PLAN-001 | Sol | Görev planı ve Orvant`.

- **gpt-6-luna low/medium:** Net sözleşmeli UI sunumu, basit mapping/config ve dokümantasyon. Medium, birden çok UI durumunun birleştiği kartlarda.
- **gpt-6-sol medium:** Parser, import resolution, backend analizi, API/entegrasyon, ölçüm ve çok modüllü işler.
- **gpt-6-sol high:** Yetki ve özel kod güvenliği, veri bütünlüğü, asenkron iş yaşam döngüsü, RAG, incremental silme, PR/webhook ve sınır incelemeleri. Gerekçe kartta yazılıdır.
- **gpt-6-astra:** Göreve atanmaz. Ana sohbette yalnız esaslı çözümsüz mimari belirsizlik kanıtla yükseltilirse kullanılır.

Her karttaki model/effort bir başlangıç hipotezidir; maliyet veya başarı garantisi değildir. Her göreve otomatik ayrı inceleme sohbeti açılmaz. T38 ve T39 riskli güvenlik ve birleşik modül sınırlarını hedefli bağımsız Sol incelemeleridir. Başarısız test önce görev sahibince düzeltilir; iki farklı başarısız yaklaşımın kısa kanıtı proje sorumlusuna aktarılır. Yeni sohbetler sadece kullanıcı/proje sorumlusu yönlendirmesiyle, hazır görev kartı için başlatılır. Kaynak: [resmî model seçimi rehberi](https://developers.openai.com/api/docs/guides/model-selection).
