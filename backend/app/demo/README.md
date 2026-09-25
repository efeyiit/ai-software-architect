# Yerel portföy demosu

Bu uygulama üretim API'sinden ayrıdır. Yalnız `127.0.0.1:8765` üzerinde
çalışır, `frontend/dist` dosyalarını sunar ve `/demo/meta`, `/demo/chat`
uçlarını açar. Üretim `/auth` ve `/api/repositories` yollarını bağlamaz;
GitHub OAuth oturumu, özel repository, kullanıcı tokenı ve PostgreSQL verisi
bu uygulamaya aktarılmaz. Tek veri kaynağı `fixture.py` içindeki paketlenmiş
sentetik TypeScript dosyasıdır. Ürün sayfalarındaki örnek veri de
örnektir; canlı repository analizi olarak sunulmamalıdır.

Proje kökünden tek başlatma komutu:

```powershell
uv run --directory backend python -m app.demo
```

Başlatıcı frontend değiştiğinde derler, bir yerel model worker ve ayrı bir site süreci açar; siteyi
`http://127.0.0.1:8765/demo` adresinde sunar. Model worker yalnız
`127.0.0.1:8766` dinler. Her başlangıçta yeni rastgele token üretilir ve
yalnız bu iki child sürecin ortamına verilir. Komut satırına, loga, meta
yanıtına ve dosyaya yazılmaz.
Port doluysa farklı porta sessizce geçmez; mümkünse
portu kullanan PID'yi bildirir. Başlatıcı kapatılınca iki child süreci
de kapatır. Frontend için kurulu `node_modules`, `training/.venv` ve yerel
model ağırlıkları önceden mevcut olmalıdır; indirme veya eğitim yapmaz.

`GET /demo/meta` yanıtında `mode=local_demo`, `label=Yerel demo`,
`data_origin=bundled_synthetic` ve gerçek model durumu `loading`, `ready`
veya `unavailable` bulunur. `ready` yalnız model worker'ın `/health` yanıtı
hazır olduğunu doğrulayınca döner. `POST /demo/chat` T21'in kaynak alıntısı
doğrulanan `ChatResponse` biçimindedir. Yerel model hazır değilken yanıt
`unavailable` olur. Geçersiz alıntı `rejected` olur; yalnız geçerli alıntılar
`answered` ve `origin=ai` alır. Qdrant bu sentetik fixture için bellekte
kurulur; ürün veritabanını veya harici vector servisini kullanmaz.

Bu demo yerel modelin gerçek semantik doğruluğu veya üretim OAuth bağlantısı
için bir iddia değildir. Kaynak bağlantısı, alıntı ve SHA kullanıcı tarafından
incelenebilir. Her iki servis de loopback'e bağlanır; POST isteklerinde yabancı
`Origin` reddedilir.
