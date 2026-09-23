# GitHub kayıt ve yayın akışı

Bu proje public GitHub reposunda görev bazında izlenir. Tek Git yazıcısı GIT-001 çalışanıdır; diğer çalışanlar kendi görev dosyalarını ve doğrulama kanıtlarını proje sorumlusuna teslim eder. Orvant'ın tek yazıcısı proje sorumlusudur. Git yazıcısı yerel `.project/` kaydını veya ürün kodunu görev sahibi yerine değiştirmez.

## Bir görevden bir commit'e

1. Görev kartındaki kabul koşulları, ilgili testler ve belge çıktısı bitmiş olmalı. Açık hata veya eksik koşul varsa görev tamamlandı diye commitlenmez.
2. Görev sahibinden görev ID'si, değişen dosyaların tam listesi, çalıştırılan doğrulamalar ve sonuçları alınır. Başka çalışanın hâlâ değiştirdiği dosya pakete katılmaz.
3. Yalnız listelenmiş dosyalar tek tek stage edilir; `git add .` kullanılmaz. `git diff --cached --stat`, `git diff --cached --check` ve staged diff incelenir. Sır, özel kod, müşteri bilgisi, yerel yol, log ve üretilmiş çıktı public kapsama giremez.
4. Doğrulanmış anlamlı görev için `<type>(<task-id>): <kısa sonuç>` biçiminde tek commit oluşturulur. Komut başına veya dosya başına commit yapılmaz; yapılmamış özellik başarı diye yazılmaz.
5. Commit ilgili dala push edilir. Yerel commit SHA ile uzak dal HEAD SHA eşitliği kontrol edilir. Push başarısızsa yayımlandı denmez. CI varsa gerçek sonucu ayrıca kaydedilir; CI yoksa bu açıkça belirtilir.

İlk planlama adımı `docs(PLAN-001): record project task plan` gibi adlandırılır. Ürün kodu sonraki doğrulanmış görevlerde ayrı commitlerle gelir. Force push veya geçmişi yeniden yazma rutin akışta kullanılmaz.

## Public sınır

`.project/` yerel Orvant state ve üretilmiş görünümler içerir; public repoya eklenmez. Kişisel vault, Codex oturumları, ekler, `.env`, API anahtarları, credential dosyaları, müşteri verisi, yerel loglar, çalışma taslakları ve `outputs/` yayımlanmaz. Public belgelerde repo köküne göre göreli yollar kullanılır. Şüpheli içerik bulunduğunda değerleri çıktıya basmadan yayın paketi durdurulur ve proje sorumlusuna bildirilir.

Orvant ve Beyin, geliştirme sırasında görev/kanıt ve özel not yönetimi için kullanılan dış araçlardır; Ariadne uygulamasının çalışma zamanı bağımlılıkları veya bu projenin geliştirdiği bileşenler değildir. Üçüncü taraf kaynak kodu ya da belgesi, lisansı ve yeniden kullanım koşulları doğrulanmadan public repoya kopyalanmaz; kaynak bağlantısı tek başına yeniden kullanım izni sağlamaz ([GitHub lisans rehberi](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)).

GitHub hesabı ve repo görünürlüğü ilk kurulumda doğrulanır. Hesap yetkisi biterse güvenli tarayıcı veya device girişini kullanıcı tamamlar; parola veya token sohbetten istenmez. Bu süreç arka planda sürekli çalışan bir izleyici değildir: her yeni commit, görev tesliminden sonra açık bir çalışma adımıdır.
