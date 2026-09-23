
# AI Software Architect  
## Software Design Document

**Project Type:** AI-Powered Developer Tool / SaaS  
**Version:** 1.0  
**Primary Platform:** Web  
**Status:** Design Phase

---

# 1. Project Overview

AI Software Architect, bir GitHub repository'sini analiz ederek yazılım geliştiricilere projenin mimarisi, kod kalitesi, bağımlılıkları, test yapısı ve dokümantasyonu hakkında otomatik analiz sağlayan AI destekli bir geliştirici aracıdır.

Kullanıcı sisteme bir GitHub repository bağlantısı verir.

Sistem repository içerisindeki kaynak kodları analiz eder ve aşağıdaki çıktıları üretir:

- Proje özeti
- Dosya ve modül açıklamaları
- Mimari yapı
- Dependency Graph
- UML diyagramları
- Code Smell tespiti
- SOLID ihlalleri
- Refactoring önerileri
- Test analizi
- Güvenlik önerileri
- README üretimi
- API dokümantasyonu
- Teknik borç analizi

Sistemin temel amacı büyük veya yabancı bir kod tabanını anlamak için gereken süreyi önemli ölçüde azaltmaktır.

---

# 2. Problem Statement

Bir geliştirici yeni bir projeye katıldığında genellikle büyük miktarda kaynak kodu manuel olarak incelemek zorundadır.

Örneğin:

```text
src/
 ├── controllers/
 ├── services/
 ├── repositories/
 ├── models/
 ├── middleware/
 └── tests/
```

Bir geliştiricinin aşağıdaki soruların cevaplarını bulması uzun sürebilir:

- Proje ne yapıyor?
- Sistem hangi mimariyi kullanıyor?
- Hangi sınıf hangi sınıfa bağlı?
- Kritik modüller hangileri?
- Test edilmeyen bölümler nereler?
- Kod kalitesi nasıl?
- Refactoring gereken yerler nereler?
- Güvenlik problemi olabilir mi?
- API yapısı nasıl?
- Projeyi çalıştırmak için ne gerekiyor?

AI Software Architect bu süreci otomatikleştirmeyi amaçlar.

---

# 3. Project Goal

Sistemin temel hedefi:

> Bir GitHub repository'sini analiz ederek geliştiricinin projeyi hızlı şekilde anlamasını sağlayan AI destekli bir yazılım mimarisi analiz platformu oluşturmak.

Sistem yalnızca LLM'e kod gönderip cevap alan basit bir chatbot olmayacaktır.

Analiz sürecinde:

- GitHub API
- Static Code Analysis
- AST Parsing
- RAG
- Vector Search
- LLM
- Graph Analysis

birlikte kullanılacaktır.

---

# 4. Target Users

## 4.1 Junior Developers

Yeni girdikleri projeyi daha hızlı anlamak isteyen geliştiriciler.

## 4.2 Software Engineers

Büyük repository'leri analiz etmek isteyen geliştiriciler.

## 4.3 Technical Leads

Kod kalitesi ve mimari sorunları görmek isteyen ekip liderleri.

## 4.4 Open Source Contributors

Katılmak istedikleri açık kaynak projelerin yapısını hızlıca öğrenmek isteyen geliştiriciler.

## 4.5 Students

GitHub projelerini inceleyerek yazılım mimarisini öğrenmek isteyen öğrenciler.

---

# 5. Main User Flow

Ana kullanıcı deneyimi mümkün olduğunca basit olacaktır.

```text
User
 ↓
Login
 ↓
GitHub Repository URL
 ↓
Analyze Repository
 ↓
Repository Download
 ↓
Code Parsing
 ↓
Static Analysis
 ↓
Vector Embedding
 ↓
AI Analysis
 ↓
Architecture Report
 ↓
Dashboard
```

Örneğin kullanıcı:

```text
https://github.com/example/ecommerce-api
```

adresini sisteme girer.

Sonrasında:

```text
Analyze Repository
```

butonuna basar.

Sistem analizi başlatır.

---

# 6. Dashboard

Analiz tamamlandıktan sonra kullanıcı aşağıdaki dashboard'u görür.

```text
--------------------------------------------------

E-Commerce API

Language:
C#

Framework:
ASP.NET Core

Files:
237

Classes:
84

API Endpoints:
31

--------------------------------------------------

Architecture

Layered Architecture

Controller
↓
Service
↓
Repository
↓
Database

--------------------------------------------------

Analysis

Code Quality

Testing

Security

Documentation

Architecture

--------------------------------------------------

Detected Issues

Critical: 2

High: 6

Medium: 18

Low: 34

--------------------------------------------------
```

Dashboard'un sol tarafında navigasyon bulunacaktır.

```text
Overview

Architecture

Dependencies

Code Quality

Security

Testing

Documentation

AI Assistant
```

---

# 7. Core Features

## 7.1 Repository Analyzer

GitHub repository'sini sisteme getirir.

Görevleri:

- Repository metadata alma
- Branch bilgisi
- Dosya ağacı oluşturma
- Programlama dilini belirleme
- Framework tahmini
- Kaynak kod dosyalarını filtreleme

Desteklenmeyen dosyalar analizden çıkarılır.

Örneğin:

```text
node_modules
dist
build
vendor
.exe
.dll
.jpg
.png
```

---

# 8. Project Overview Generator

Sistem repository'nin genel olarak ne yaptığını belirlemeye çalışacaktır.

Örnek çıktı:

```text
This repository is an ASP.NET Core REST API
designed for an e-commerce application.

Main modules:

Authentication
Products
Orders
Payments
Inventory
Users
```

Ayrıca kullanılan teknolojiler listelenir.

```text
ASP.NET Core

Entity Framework Core

PostgreSQL

JWT

Redis

Docker
```

---

# 9. File Explanation System

Kullanıcı herhangi bir dosyaya tıklayabilir.

Örneğin:

```text
AuthService.cs
```

AI açıklaması:

```text
AuthService kullanıcı authentication işlemlerini
yönetmektedir.

Temel görevleri:

- Login
- Password validation
- JWT generation
- Refresh token management
```

Böylece kullanıcı kodu tamamen okumadan dosyanın sorumluluğunu anlayabilir.

---

# 10. Architecture Detection

Sistem repository içerisinde kullanılan mimari yapıyı analiz eder.

Tespit edilebilecek örnek mimariler:

- MVC
- Layered Architecture
- Clean Architecture
- Hexagonal Architecture
- Microservices
- Modular Monolith
- Event Driven Architecture

Örneğin:

```text
Presentation

↓

Application

↓

Domain

↓

Infrastructure
```

Sistem bunun Clean Architecture olduğunu tahmin edebilir.

Tahmin kesin bilgi olarak gösterilmemelidir.

Örneğin:

```text
Detected Architecture:

Clean Architecture

Confidence: High
```

---

# 11. Dependency Graph

Kod içerisindeki bağımlılıklar analiz edilir.

Örneğin:

```text
UserController
       ↓
UserService
       ↓
UserRepository
       ↓
DatabaseContext
```

Frontend üzerinde interaktif graph olarak gösterilir.

Kullanıcı node'a tıklayarak ilgili dosyaya gidebilir.

---

# 12. UML Generator

Sistem kod yapısından otomatik UML oluşturabilir.

İlk versiyonda Mermaid kullanılabilir.

Örnek:

```text
User

id
name
email

↓

Order

id
userId
totalPrice
```

İleri versiyonlarda PlantUML eklenebilir.

Desteklenecek diyagramlar:

- Class Diagram
- Sequence Diagram
- Component Diagram

---

# 13. Static Code Analysis

Her problemi doğrudan LLM'e sormak yerine bazı kontroller normal kod analiz araçlarıyla yapılmalıdır.

Bu proje için önemli bir tasarım kararıdır.

Örneğin sistem şunları algoritmik olarak tespit edebilir:

- Çok uzun fonksiyon
- Çok büyük sınıf
- Duplicate code
- Magic number
- Deep nesting
- Çok fazla parameter
- Circular dependency
- Unused imports

Sonrasında AI bu bulguları açıklayabilir.

---

# 14. AST Analysis

AST:

```text
Abstract Syntax Tree
```

Kaynak kodunun yapısal temsilidir.

Örneğin:

```python
def login(username, password):
    ...
```

AST sayesinde sistem bunun bir fonksiyon olduğunu anlayabilir.

AST kullanılarak çıkarılabilecek bilgiler:

- Classes
- Functions
- Methods
- Imports
- Variables
- Function Calls
- Inheritance
- Dependencies

Python için:

```text
tree-sitter
```

kullanılması önerilir.

Tree-sitter birçok dili desteklediği için proje büyüdüğünde avantaj sağlar.

---

# 15. Code Smell Detection

Sistem aşağıdaki code smell türlerini tespit etmeye çalışacaktır.

### Long Method

Örneğin:

```text
processOrder()

240 lines
```

### God Class

Örneğin:

```text
OrderService

1500 lines

41 methods
```

### Deep Nesting

```text
if
  if
    if
      if
        if
```

### Duplicate Code

Benzer kod bloklarının farklı yerlerde tekrar kullanılması.

### Magic Numbers

Örneğin:

```text
if status == 713
```

yerine:

```text
if status == PAYMENT_PENDING
```

önerilebilir.

---

# 16. SOLID Analyzer

AI aşağıdaki prensiplere göre kod hakkında yorum üretebilir.

## Single Responsibility Principle

Bir sınıf çok fazla farklı göreve sahipse işaretlenebilir.

Örneğin:

```text
UserService
```

aynı anda:

```text
Create User

Send Email

Generate PDF

Process Payment

Write Logs
```

yapıyorsa sistem bunu problem olarak gösterebilir.

---

# 17. Refactoring Assistant

Sistem yalnızca problem göstermeyecek.

Aynı zamanda çözüm önerecektir.

Örneğin:

```text
Problem:

OrderService has too many responsibilities.
```

Öneri:

```text
OrderService

↓

PaymentService

InventoryService

NotificationService
```

---

# 18. Testing Analyzer

Test klasörleri analiz edilir.

Sistem aşağıdaki bilgileri çıkarır:

```text
Services:

23

Tested Services:

14

Potentially Untested Services:

9
```

Buradaki sonuç gerçek coverage ile karıştırılmamalıdır.

Gerçek code coverage bilgisi mevcutsa ayrıca kullanılabilir.

---

# 19. Test Generator

AI test edilmeyen kodlar için test önerileri oluşturabilir.

Örneğin:

```text
OrderService

Suggested Tests

- Create order successfully
- Product out of stock
- Invalid user
- Payment failure
- Database failure
```

İleri versiyonda otomatik test kodu da oluşturulabilir.

---

# 20. Security Analysis

İlk sürümde temel güvenlik kontrolleri yapılabilir.

Örneğin:

- Hardcoded API key
- Hardcoded password
- SQL query construction
- JWT validation problems
- Missing authentication
- Sensitive logs
- Environment secrets

Örnek:

```text
HIGH SECURITY RISK

File:

DatabaseService.cs

Possible hardcoded database password detected.
```

Güvenlik bulguları kesin açık olarak sunulmamalıdır.

```text
Potential Security Issue
```

gibi ifadeler kullanılmalıdır.

---

# 21. Documentation Generator

Sistem repository için otomatik README üretebilir.

README içerisinde:

```text
Project Description

Requirements

Installation

Environment Variables

Running Locally

Docker Setup

API Documentation

Project Structure

Testing
```

bulunabilir.

---

# 22. API Documentation Generator

Backend API endpointleri tespit edilir.

Örneğin:

```text
POST /api/login
```

Sistem açıklama oluşturur.

```text
Authenticates a user.

Request

email
password

Response

JWT access token
refresh token
```

---

# 23. AI Repository Chat

Kullanıcı analiz edilen repository hakkında AI'a soru sorabilir.

Örneğin:

```text
Login sistemi nasıl çalışıyor?
```

AI repository'den ilgili dosyaları bulur.

Örneğin:

```text
AuthController.cs

AuthService.cs

JwtService.cs
```

sonrasında cevap üretir.

Başka örnek:

```text
Ödeme sistemi hangi sınıflara bağlı?
```

AI:

```text
PaymentController

↓

PaymentService

↓

StripeProvider

↓

OrderRepository
```

şeklinde cevap verebilir.

---

# 24. Why RAG Is Needed

Büyük repository'nin tamamını tek bir LLM isteğine göndermek mümkün değildir.

Örneğin proje:

```text
5000 files
```

içeriyor olabilir.

Bu nedenle sistem kodu küçük parçalara ayırır.

```text
Repository

↓

Files

↓

Classes

↓

Functions

↓

Chunks
```

Her chunk embedding'e çevrilir.

---

# 25. Vector Database

Vector database olarak:

```text
Qdrant
```

kullanılacaktır.

Örneğin kullanıcı:

```text
Where is JWT generated?
```

diye sorar.

Sistem önce vector search yapar.

İlgili kod parçalarını bulur.

Örneğin:

```text
JwtService.cs

AuthService.cs

TokenConfig.cs
```

yalnızca bunlar LLM'e gönderilir.

---

# 26. RAG Pipeline

```text
User Question

↓

Embedding

↓

Qdrant Search

↓

Relevant Code Chunks

↓

Prompt Builder

↓

LLM

↓

Answer
```

Bu sistem sayesinde büyük repository'lerde AI çok daha verimli çalışabilir.

---

# 27. Repository Analysis Pipeline

Tam analiz pipeline'ı:

```text
GitHub URL

↓

Repository Fetcher

↓

File Filter

↓

Language Detector

↓

Code Parser

↓

AST Generator

↓

Dependency Analyzer

↓

Static Analyzer

↓

Code Chunker

↓

Embedding Generator

↓

Qdrant

↓

LLM Analyzer

↓

Report Generator

↓

Frontend Dashboard
```

---

# 28. System Architecture

Projenin genel mimarisi:

```text
                 React Frontend

                       │

                       ▼

                  FastAPI API

                       │

     ┌─────────────────┼─────────────────┐

     ▼                 ▼                 ▼

GitHub Service     Analysis Engine     AI Engine

     │                 │                 │

GitHub API         AST Parser           LLM

                       │                 │

                 Static Analysis        RAG

                       │                 │

                       ▼                 ▼

                  PostgreSQL          Qdrant
```

---

# 29. Frontend

Teknolojiler:

```text
React

TypeScript

Tailwind CSS
```

Ana sayfalar:

```text
/login

/dashboard

/repository/:id

/repository/:id/architecture

/repository/:id/dependencies

/repository/:id/issues

/repository/:id/security

/repository/:id/testing

/repository/:id/chat
```

---

# 30. Backend

Backend:

```text
Python

FastAPI
```

Örnek klasör yapısı:

```text
backend/

app/

 api/

 services/

 analyzers/

 parsers/

 models/

 repositories/

 ai/

 rag/

 security/

 database/

 main.py
```

---

# 31. Main Backend Modules

## GitHubService

Repository işlemleri.

```text
fetchRepository()

getRepositoryMetadata()

getFiles()
```

## ParserService

Kaynak kodunu parse eder.

```text
parseFile()

extractClasses()

extractFunctions()

extractImports()
```

## DependencyAnalyzer

Bağımlılıkları çıkarır.

## StaticAnalyzer

Kod kalite kontrollerini yapar.

## RAGService

Embedding ve vector search işlemlerini gerçekleştirir.

## AIService

LLM iletişimini yönetir.

---

# 32. Database

Ana database:

```text
PostgreSQL
```

---

# 33. Data Model

## User

```text
id

email

password_hash

github_id

created_at
```

## Repository

```text
id

user_id

github_url

name

language

framework

status

created_at
```

## File

```text
id

repository_id

path

language

size

summary
```

## Analysis

```text
id

repository_id

type

result

severity

created_at
```

## Dependency

```text
id

repository_id

source_file

target_file

dependency_type
```

## CodeIssue

```text
id

repository_id

file_id

line_number

issue_type

severity

description

suggestion
```

---

# 34. Example API

Repository oluştur:

```text
POST /api/repositories
```

Body:

```json
{
  "github_url": "https://github.com/user/project"
}
```

Analiz başlat:

```text
POST /api/repositories/{id}/analyze
```

Repository bilgisi:

```text
GET /api/repositories/{id}
```

Issues:

```text
GET /api/repositories/{id}/issues
```

Dependencies:

```text
GET /api/repositories/{id}/dependencies
```

AI chat:

```text
POST /api/repositories/{id}/chat
```

---

# 35. AI Architecture

İlk versiyonda tek AI servis kullanılmalıdır.

```text
Code Context

+

Static Analysis Results

+

User Question

↓

LLM
```

Başlangıçta multi-agent sistem kurmak gereksiz karmaşıklık yaratacaktır.

---

# 36. Future Multi-Agent Architecture

Proje ilerlediğinde farklı ajanlar oluşturulabilir.

## Architect Agent

Mimariyi analiz eder.

## Security Agent

Güvenlik risklerini inceler.

## Testing Agent

Test yapısını analiz eder.

## Refactoring Agent

Kod iyileştirmeleri önerir.

## Documentation Agent

README ve dokümantasyon üretir.

Sistem:

```text
Orchestrator Agent

├── Architect Agent
├── Security Agent
├── Testing Agent
├── Refactor Agent
└── Documentation Agent
```

şeklinde çalışabilir.

---

# 37. LLM Prompt Strategy

LLM'e:

```text
Analyze this repository.
```

demek yerine structured prompt kullanılmalıdır.

Örneğin:

```text
ROLE

You are a senior software architect.

TASK

Analyze the supplied class.

CHECK

Responsibilities
Dependencies
SOLID violations
Potential design problems
Refactoring opportunities

OUTPUT

Return JSON.
```

Bu şekilde sonuçların backend tarafından işlenmesi kolaylaşır.

---

# 38. Structured AI Output

Örnek:

```json
{
  "issues": [
    {
      "type": "SRP_VIOLATION",
      "severity": "medium",
      "file": "UserService.cs",
      "reason": "Class handles authentication and email delivery.",
      "suggestion": "Extract email logic into NotificationService."
    }
  ]
}
```

Bu yaklaşım LLM cevabının doğrudan UI'a dönüştürülmesini kolaylaştırır.

---

# 39. Security

Özel repository analizinde kullanıcı kodlarının korunması önemlidir.

Temel önlemler:

- GitHub OAuth
- Token encryption
- HTTPS
- Rate limiting
- Input validation
- Repository permission kontrolü
- Secret logging yapılmaması

GitHub tokenları plain text olarak database'de saklanmamalıdır.

---

# 40. Performance

Repository analizi uzun sürebileceği için analiz işlemleri HTTP isteği içerisinde tamamen yapılmamalıdır.

İleri sürümlerde:

```text
FastAPI

↓

Task Queue

↓

Worker
```

mimarisi kullanılabilir.

Örneğin:

```text
Celery

Redis
```

veya benzer bir queue sistemi.

---

# 41. Caching

Aynı commit tekrar analiz edilmemelidir.

Repository için:

```text
commit SHA
```

saklanabilir.

Son analiz edilen SHA aynıysa mevcut analiz sonucu kullanılabilir.

---

# 42. Incremental Analysis

İleri versiyonda bütün repository tekrar analiz edilmek yerine yalnızca değişen dosyalar analiz edilebilir.

```text
Old Commit

↓

Git Diff

↓

Changed Files

↓

Partial Analysis
```

Bu özellik büyük repository'lerde önemli performans avantajı sağlar.

---

# 43. Error Handling

Sistem aşağıdaki durumları düzgün yönetmelidir.

```text
Repository not found

Private repository access denied

Unsupported language

GitHub API rate limit

LLM timeout

Invalid repository

Repository too large

Analysis failed
```

---

# 44. Logging

Sistem önemli işlemleri loglamalıdır.

Örneğin:

```text
Repository cloned

Parsing started

Parsing finished

Files processed: 312

Embeddings created: 1432

Analysis completed
```

Ancak kaynak kod veya gizli bilgiler loglara yazılmamalıdır.

---

# 45. Testing Strategy

## Unit Tests

Özellikle:

```text
Parser

Dependency Analyzer

Code Chunker

Static Analyzer
```

test edilmelidir.

## Integration Tests

```text
GitHub API

Database

Qdrant

LLM Provider
```

entegrasyonları test edilmelidir.

## End-to-End Test

```text
Repository URL

↓

Analysis

↓

Dashboard
```

akışının tamamı test edilmelidir.

---

# 46. Deployment

Uygulamanın tüm parçaları Docker container olarak çalıştırılabilir.

```text
Docker Compose

├── frontend
├── backend
├── postgres
├── qdrant
└── redis
```

İleri aşamada cloud deployment yapılabilir.

---

# 47. Technology Stack

## Frontend

```text
React
TypeScript
Tailwind CSS
```

## Backend

```text
Python
FastAPI
```

## AI

```text
LLM API
RAG
Embeddings
```

## Code Analysis

```text
Tree-sitter
Custom Static Analysis
```

## Database

```text
PostgreSQL
```

## Vector Database

```text
Qdrant
```

## Diagrams

```text
Mermaid

PlantUML
```

## DevOps

```text
Docker

GitHub Actions
```

---

# 48. MVP

İlk sürüm kesinlikle çok büyük tutulmamalıdır.

MVP yalnızca aşağıdakileri yapmalıdır:

```text
GitHub URL al

↓

Repository dosyalarını getir

↓

File Tree göster

↓

Programlama dilini belirle

↓

Dosyaları analiz et

↓

File Summary üret

↓

Project Summary üret

↓

Basit Dependency Graph göster

↓

Repository hakkında AI'a soru sor
```

Bu sürüm bile GitHub üzerinde yayınlanabilir.

---

# 49. Development Roadmap

## V1 — Repository Intelligence

Amaç:

Repository'yi anlamak.

Özellikler:

- GitHub repository import
- File tree
- Language detection
- File summaries
- Project summary
- RAG
- Repository chat

---

## V2 — Architecture Intelligence

Amaç:

Kod yapısını anlamak.

Özellikler:

- AST parsing
- Dependency Graph
- Class detection
- Function detection
- Architecture detection
- UML generation

---

## V3 — Code Quality Intelligence

Amaç:

Kod problemlerini bulmak.

Özellikler:

- Code smell
- SOLID analysis
- Refactoring suggestions
- Test analysis
- Security analysis

---

## V4 — AI Engineering Platform

Amaç:

Projeyi profesyonel geliştirici aracına dönüştürmek.

Özellikler:

- Multi-agent system
- Automated documentation
- Test generation
- Pull Request analysis
- Incremental repository analysis
- GitHub integration
- Issue generation

---

# 50. Future Feature — Pull Request Review

Kullanıcı GitHub hesabını bağlar.

Yeni Pull Request açıldığında sistem değişen kodları analiz eder.

Örneğin:

```text
PR #124

Potential Problems

2 security issues

1 architecture issue

3 missing tests
```

AI açıklama oluşturabilir.

---

# 51. Future Feature — Architecture Evolution

Sistem repository'nin zaman içerisindeki değişimini gösterebilir.

Örneğin:

```text
January

45 classes

↓

March

71 classes

↓

June

120 classes
```

ve teknik borcun zaman içerisinde artıp azaldığını gösterebilir.

---

# 52. Risks

## LLM Hallucination

AI yanlış yorum yapabilir.

Çözüm:

Static analysis sonuçları ile LLM yorumları ayrılmalıdır.

Örneğin:

```text
Static Analysis Finding
```

ve

```text
AI Recommendation
```

farklı gösterilmelidir.

---

## Large Repositories

Çok büyük repository'ler pahalı olabilir.

Çözüm:

- File filtering
- Chunking
- RAG
- Caching
- Incremental analysis

---

## Multiple Languages

Her programlama dilinin syntax yapısı farklıdır.

İlk sürümde 1-2 dil desteklemek daha doğru olacaktır.

Önerilen başlangıç:

```text
Python

TypeScript
```

Daha sonra:

```text
Java

C#

C++
```

eklenebilir.

---

# 53. Success Metrics

Projenin başarısı şu metriklerle ölçülebilir:

```text
Repository analysis time

Supported languages

Number of correctly detected dependencies

RAG answer accuracy

User analysis completion rate

AI response latency

Analysis cost per repository
```

---

# 54. Recommended Initial Scope

İlk sürüm için:

```text
Frontend

React
TypeScript
Tailwind

Backend

FastAPI

Database

PostgreSQL

Repository

GitHub API

Parser

Tree-sitter

Vector DB

Qdrant

AI

LLM API

Diagram

Mermaid
```

yeterlidir.

İlk aşamada:

```text
Kubernetes

Microservices

Kafka

Complex Agents
```

eklemek gereksizdir.

Proje büyüdükçe eklenmelidir.

---

# 55. Example Final User Experience

Kullanıcı repository ekler:

```text
github.com/example/ecommerce
```

Sistem birkaç analiz aşamasından geçirir.

Dashboard:

```text
E-Commerce Backend

Primary Language

Python

Framework

FastAPI

Architecture

Layered Architecture

Files

187

Classes

53

Functions

412
```

Sistem ardından:

```text
Architecture

API
 ↓
Service
 ↓
Repository
 ↓
PostgreSQL
```

gösterir.

Issues:

```text
HIGH

PaymentService has excessive responsibilities.

MEDIUM

OrderService contains deeply nested logic.

LOW

Multiple magic numbers detected.
```

AI Assistant:

```text
USER

Sipariş oluşturulurken hangi sınıflar çalışıyor?

AI

The request starts from OrderController.

OrderController
↓
OrderService
↓
InventoryService
↓
PaymentService
↓
OrderRepository
```

Bu, projenin temel ürün deneyimidir.

---

# 56. CV Presentation

Proje tamamlandığında CV'de şu şekilde anlatılabilir:

**AI Software Architect — AI-powered repository analysis platform**

Developed an AI-powered developer tool capable of analyzing GitHub repositories, extracting code structure using AST parsing, visualizing dependencies, detecting code-quality issues, and enabling repository-level semantic search using RAG.

Technologies:

```text
Python
FastAPI
React
TypeScript
PostgreSQL
Qdrant
Tree-sitter
Docker
GitHub API
LLMs
RAG
```

---

# 57. Project Philosophy

Bu projenin amacı yalnızca:

```text
AI API çağrısı yapmak
```

değildir.

Asıl amaç:

```text
Software Engineering
+
Static Analysis
+
AI
+
Search
+
System Design
```

alanlarını gerçek bir ürün içerisinde birleştirmektir.

Projenin en güçlü tarafı da budur.

Kullanıcı tek bir repository bağlantısı verir.

Sistem ise repository'yi:

> okunabilir, aranabilir, görselleştirilebilir ve analiz edilebilir bir yazılım mimarisi haritasına dönüştürür.