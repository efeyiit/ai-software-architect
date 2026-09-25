# T17 — Dosya ve proje özetleri

`summarize_repository(snapshot, structures)` tek bir yetkilendirilmiş GitHub commit
snapshot'ının beş parser çıktısını özetler. Çıktı `snapshot.repository_id` ve
`snapshot.commit_sha` taşır. Semboller, importlar, ana modül adayları ve dil/marker
teknolojileri `static` kaynak konumlarıyla gelir. Ana modüller yalnız adaydır.
Sağlayıcı yoksa dosya sorumluluğu ve proje amacı, sözdiziminden
kanıtlanamadığı için `Unknown` kalır. Parser hatası
olan dosyada yapısal iddia üretilmez.

Parser çıktıları kendi başlarına repository ID veya SHA taşımaz. Çağıran kod,
aynı SHA'dan alınmış parser sonuçlarını ve yetki denetimini sağlamak zorundadır.
Modül, parser dosya kümesini snapshot'ın desteklenen dosyalarıyla eşleştirir;
farklı/eksik dosyayı ve kapsam dışı kaynak metnini reddeder. Bu denetim, içerik
SHA'sını bağımsız olarak ispatlamaz. İçe alınmayan veya desteklenmeyen dosyalar
özetin belirsizlik sınırıdır.

`provider` verilmezse `ai_status="unavailable"` olur; statik özet AI çıktısı
olarak sunulmaz. Sağlayıcı verilmesi açık bir opt-in'dir. Yalnız çağıranın verdiği
desteklenen dosya metinleri sağlayıcıya geçer; ağ istemcisi ve dış sağlayıcı kodu
bu modülde yoktur. Sağlayıcı `ProviderOutput` biçiminde dosya iddiası, kategori
(`responsibility`, `purpose`, `module`, `technology`), kaynak satırı ve kaynakta
birebir bulunan alıntı döndürür. Yanlış/eksik alıntı veya
kapsam dışı dosya tüm AI iddialarını reddeder (`ai_status="rejected"`), statik
bulgular kalır. Doğru alıntı yorumun doğruluğunu ispatlamaz; AI iddiaları ayrı
`origin="ai"` alanında kalır. Doldurulan sorumluluk ve amaç alanları da doğrudan
`responsibility_citations` ve `purpose_citations` taşır. Sağlayıcı entegrasyonu ve dışarı kod gönderme
politikası üst katmanın kararıdır.

Hedefli kontrol: `cd backend; uv run pytest tests/summaries -q`.
Beş gerçek parser çıktısı, eksik dosya, parser hatası, geçerli/geçersiz AI
alıntısı ve eksik/kapsam dışı kaynak metni test edilir. API/UI bağlantısı T25/T27
görevlerinde yapılacaktır.
