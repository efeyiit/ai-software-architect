# Görev haritası

Tüm işler `todo` başlar; hazır olma durumu Orvant tarafından hesaplanır. Karttaki her davranış ve hedefli test aynı sohbetin işidir.

| ID | İş | Önkoşul | Model |
| --- | --- | --- | --- |
| [T01](tasks/T01.md) | Uygulama iskeleti ve analiz sözleşmeleri | — | gpt-6-sol medium |
| [T02](tasks/T02.md) | PostgreSQL şeması ve sahiplik sınırları | T01 | gpt-6-sol medium |
| [T03](tasks/T03.md) | GitHub herkese açık repository alma | T01, T02 | gpt-6-sol medium |
| [T04](tasks/T04.md) | OAuth ve özel repository yetkisi | T02, T03 | gpt-6-sol high |
| [T05](tasks/T05.md) | Python AST çıkarımı | T01, T03 | gpt-6-sol medium |
| [T06](tasks/T06.md) | TypeScript AST çıkarımı | T01, T03 | gpt-6-sol medium |
| [T07](tasks/T07.md) | Java AST çıkarımı | T01, T03 | gpt-6-sol medium |
| [T08](tasks/T08.md) | C# AST çıkarımı | T01, T03 | gpt-6-sol medium |
| [T09](tasks/T09.md) | C++ AST çıkarımı | T01, T03 | gpt-6-sol medium |
| [T10](tasks/T10.md) | Bağımlılık çözümü ve çevrimler | T05, T06, T07, T08, T09 | gpt-6-sol high |
| [T11](tasks/T11.md) | Statik kalite kontrolleri | T05, T06, T07, T08, T09, T10 | gpt-6-sol medium |
| [T12](tasks/T12.md) | Mimari tahmini | T10 | gpt-6-sol medium |
| [T13](tasks/T13.md) | SOLID ve refactor önerisi | T11, T12 | gpt-6-sol medium |
| [T14](tasks/T14.md) | Test keşfi ve coverage ayrımı | T05, T06, T07, T08, T09 | gpt-6-sol medium |
| [T15](tasks/T15.md) | Test önerisi ve kod üretimi | T14 | gpt-6-sol medium |
| [T16](tasks/T16.md) | Repository güvenlik analizi | T05, T06, T07, T08, T09 | gpt-6-sol high |
| [T17](tasks/T17.md) | Dosya ve proje özetleri | T03, T05, T06, T07, T08, T09 | gpt-6-sol medium |
| [T18](tasks/T18.md) | Mermaid ve PlantUML diyagramları | T10, T12 | gpt-6-luna low |
| [T19](tasks/T19.md) | README ve API dokümantasyonu | T03, T05, T06, T07, T08, T09 | gpt-6-sol medium |
| [T20](tasks/T20.md) | Chunk, embedding ve Qdrant indeksleme | T03, T05, T06, T07, T08, T09 | gpt-6-sol high |
| [T21](tasks/T21.md) | Kaynaklı repository sohbeti | T17, T20 | gpt-6-sol high |
| [T22](tasks/T22.md) | Queue, worker ve iş durumları | T02, T03 | gpt-6-sol high |
| [T23](tasks/T23.md) | Branch-SHA analiz önbelleği | T02, T22 | gpt-6-sol medium |
| [T24](tasks/T24.md) | Çok ajanlı analiz orkestrasyonu | T13, T14, T16, T19, T21, T22 | gpt-6-sol medium |
| [T25](tasks/T25.md) | Analiz API ve rapor birleştirme | T04, T10, T11, T12, T13, T14, T15, T16, T17, T18, T19, T20, T21, T22, T23, T24 | gpt-6-sol medium |
| [T26](tasks/T26.md) | React uygulama kabuğu | T01 | gpt-6-luna low |
| [T27](tasks/T27.md) | Genel bakış ve dosya ekranı | T25, T26 | gpt-6-luna low |
| [T28](tasks/T28.md) | Mimari ve bağımlılık ekranı | T18, T25, T26 | gpt-6-luna medium |
| [T29](tasks/T29.md) | Bulgular, güvenlik, test, doküman ekranları | T25, T26 | gpt-6-luna medium |
| [T30](tasks/T30.md) | Repository sohbet ekranı | T21, T25, T26 | gpt-6-luna medium |
| [T31](tasks/T31.md) | Incremental analiz ve silme/yeniden adlandırma | T10, T20, T22, T23, T25 | gpt-6-sol high |
| [T32](tasks/T32.md) | PR webhook, diff ve inceleme | T04, T25, T31 | gpt-6-sol high |
| [T33](tasks/T33.md) | Issue taslağı ve açık yayın eylemi | T04, T25, T32 | gpt-6-sol medium |
| [T34](tasks/T34.md) | Mimari tarihçe ve teknik borç eğilimi | T12, T25, T31 | gpt-6-sol medium |
| [T35](tasks/T35.md) | Docker ve CI çalıştırma | T25, T26, T27, T28, T29, T30, T31, T32, T33, T34, T38, T39 | gpt-6-sol medium |
| [T36](tasks/T36.md) | Uçtan uca, eval ve metrik doğrulama | T35 | gpt-6-sol medium |
| [T37](tasks/T37.md) | Gerçek demo ve CV/GitHub sunumu | T36 | gpt-6-luna low |
| [T38](tasks/T38.md) | Özel kod ve güvenlik sınırı incelemesi | T04, T16, T20, T21, T32, T33 | gpt-6-sol high |
| [T39](tasks/T39.md) | Birleşik analiz sözleşmesi incelemesi | T10, T17, T18, T21, T25, T31 | gpt-6-sol high |
