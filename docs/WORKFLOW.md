# Çalışanlarla çalışma standardı

Bu proje tüm kaynak kapsamıyla, CV/GitHub önceliği ve token verimliliği gözetilerek küçük doğrulanabilir görevlere bölünür. MVP/V1/V2 ayrımı kullanılmaz.

## Roller

| Rol | Çalışan | Görev |
|---|---|---|
| Proje sorumlusu | Ana sohbet, Astra gerektiğinde | Kapsam, zor mimari kararlar, görev dağıtımı |
| Görev planlama | PLAN-001, Sol | Görev kartları ve yetkili Orvant kurulumu |
| Geliştirme | Kartına göre Luna veya Sol | Tek doğrulanabilir sonuç, ilgili test ve belge |
| Anlatım | ANLAT-001, Luna | Kısa özet ve detaylı proje açıklaması |
| GitHub kayıtları | GIT-001, Sol; rutin işler Luna'ya devredilebilir | Repo, staging, commit, push ve uzak kayıt doğrulama |

Sohbet isimleri: `Ariadne | GÖREV-ID | Luna/Sol | Kısa iş`. Ana sohbet `Ariadne | MERKEZ | Astra | Proje sorumlusu`.

## Teslim zinciri

1. Önkoşulları tamamlanmış görev kartı seçilir. Çalışan yalnız gerekli bağlamı okur.
2. Çalışan kendi dosyalarını değiştirir ve karttaki kontrolleri yapar.
3. Kısa teslim: görev ID, dosyalar, çalıştırılan kontroller ve sonuçları, açık konular, Git'e hazır dosya listesi.
4. Gerekiyorsa risk odaklı bağımsız inceleme yapılır. Her görev otomatik Astra kontrolüne gitmez.
5. Orvant'ın belirlenmiş tek yazıcısı kanıt ve durumu günceller. Açık kabul koşulu olan görev tamamlandı sayılmaz.
6. GitHub çalışanı sabitlenmiş ilgili dosyaları açık listeyle stage eder, staged diff ve yayın kapsamını kontrol eder; doğrulanmış adımı commit/push yapar.
7. Uzak commit SHA ve varsa CI sonucu kaydedilir. Sonraki hazır göreve geçilir.

Her doğrulanmış anlamlı adım bir commit olur: `docs(PLAN-001): record project task plan` gibi. Her dosya yazımı veya test komutu ayrı commit değildir. Yerel commit, başarılı push ve başarılı CI ayrı durumlardır.

## Yetki ve dosya sahipliği

Kullanıcı bu projenin kendi GitHub hesabında public repo olarak yayımlanmasına ve doğrulanmış adımların commit edilmesine açıkça izin verdi. Bu yetki başka projelerin gizli içeriğini yayımlama izni değildir. Public repo'ya sırlar, özel kullanıcı/müşteri verileri, kişisel vault/oturum kayıtları, yerel günlükler veya yerel Orvant state körlemesine eklenmez.

GitHub çalışanı Git index/commit/push işlemlerinin tek yazıcısıdır; geliştirme çalışanları bunları yapmaz. Orvant'ın tek yazıcısı mevcut AGENTS görev paylaşımına göre hareket eder. Diğer çalışan sürmekte olan bir dosyayı commit paketine dahil etmez. GitHub çalışanı ürün kodunu yeniden tasarlamaz.

Yeni işler açık görev mesajıyla başlatılır. Sürekli izleme otomasyonu kurulmuş değildir. Çalışanlar tamamlandığında kısa teslim verir; iş bitmeden başarı iddiasında bulunmaz.

## Tekrar kullanılabilir yöntem

Kişisel beceri adı `calisanlarla-proje`. Yeni projede bu yöntemi kullanma tercihi kaydedilmiştir. Projenin hesabı, görünürlüğü ve yayınlanacak veri sınırları kendi bağlamında korunur. Skill'in yeni oturumda otomatik keşfi henüz sınanmış değildir.
