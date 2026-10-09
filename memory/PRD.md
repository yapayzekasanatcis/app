# NOVA ASİSTAN - PRD

## Original Problem Statement
Türkçe konuşan, gerçek bir özel sekreter gibi davranan kişisel yapay zekâ asistanı NOVA. Kullanıcı Bora'nın hayatını (Komagene işletme, Tiyatral Nikâh organizasyonları, Bora AI Stüdyo, kişisel yaşam, önemli tarihler, Tuğba) tek merkezden koordine eder. Google Calendar/Drive/Sheets/Gmail entegrasyonu aşamalı. OpenAI gpt-4o-mini + Whisper + TTS. Türkçe sesli ve yazılı iletişim. Düşük maliyet (hedef <1500 TL/ay).

## Architecture
- **Backend**: FastAPI + MongoDB (motor async) + Emergent Universal LLM Key
- **Auth**: Emergent-managed Google OAuth + backend tek kullanıcı allowlist (`yapayzekasanatcisi@gmail.com`); session cookie `nova_session`, HttpOnly, signed with itsdangerous
- **LLM**: `emergentintegrations.llm.chat.LlmChat` → OpenAI gpt-4o-mini
- **Live Web**: Gemini 2.5 Flash + Google Search grounding; yalnız güncel sorgularda, doğrulanabilir citation zorunlu
- **Voice**: OpenAI Whisper (STT) + OpenAI gpt-4o-mini-tts (TTS) via Emergent proxy
- **Frontend**: React 19 + React Router + Framer Motion + Shadcn UI + Tailwind
- **Theme**: Dark Warm Executive (Obsidian + Amber) — Cormorant Garamond serif + Plus Jakarta Sans

## User Personas
- **Bora** (sole user): İşletme sahibi, organizasyoncu, AI stüdyo yöneticisi. Günlük rutini karmaşık; tek merkezden kontrol ister.

## Core Requirements (static)
1. Türkçe UI/sesli yanıt
2. NOVA karakteri (sıcak, profesyonel, kısa cevap, "Bora" hitabı)
3. Push-to-talk mikrofon + sesli dinleme
4. Günlük brifing (takvim + öncelikler + bekleyen işler birleşik)
5. Tasks (bağlama göre: kişisel/komagene/tiyatral-nikâh/bora-ai-studyo) + Öncelik işareti
6. Notlar, Takvim/Etkinlikler CRUD
7. Önemli tarih hatırlatıcıları (Tuğba 10 Kasım, Komagene %50 Çiğköfte 15'i, aile)
8. Low cost (<1500 TL/ay)
9. Güvenlik: onaysız ödeme/rezervasyon/mail gönderme/etkinlik silme YOK
10. Production uygulama içeriği ve tüm private/ücretli API'ler yalnız `yapayzekasanatcisi@gmail.com` hesabına açık

## Implemented (2026-02-08)
- Backend: Auth (session/me/logout), Chat, Chat History, Briefing/today, Tasks CRUD, Notes CRUD, Events CRUD, STT, TTS
- Frontend: Login (Google), Dashboard (Bugün - brifing + öncelikler + takvim + uyarılar), Yarın, Bu Hafta, Bekleyen İşler, Öncelikler, Takvim, Komagene, Tiyatral Nikâh, Bora AI Stüdyo, Kişisel, Notlar, Ayarlar
- Floating NOVA orb (idle/listening/thinking/speaking states) + Push-to-talk + Chat panel
- 20/20 backend tests passed

## Google Workspace Integration Update (2026-10-08)
- Google OAuth modülünün ortam değişkenlerinden önce yüklenmesi nedeniyle oluşan yapılandırma hatası kod seviyesinde düzeltildi.
- Salt-okunur Calendar, Drive, Sheets ve Docs kapsamları; şifreli refresh token saklama; 10 dakikalık OAuth state süresi ve birebir callback URI kullanımı eklendi.
- `NOVA ASİSTAN — Özel Takvim` için tarih bazlı okuma ve 8 Ekim 2026 doğrulaması eklendi; adı geçen takvim yoksa birincil takvime sessiz fallback kaldırıldı.
- `NOVA İş Merkezi` ve İşler/Projeler/Rutinler sekmeleri için gerçek okuma doğrulama endpoint'i ve Ayarlar sonuç ekranı eklendi.
- Günlük brifing ve Bugün ekranındaki kodla üretilen Komagene/özel gün rutinleri kaldırıldı; rutinler yalnızca gerçek Sheets/Docs verisinden okunuyor.
- Backend regresyon testleri seri çalışmada 20/20 geçti; frontend üretim derlemesi geçti; masaüstü ve 390px mobil görünümde yatay taşma yok.
- OAuth PKCE `code_verifier` state kaydına bağlı ve şifreli saklanarak token exchange düzeltildi; gerçek Google token endpoint yanıtı HTTP 200 ile tamamlandı.
- OAuth callback access loglarında authorization code, state, token ve client secret alanları redakte ediliyor.
- Google Calendar UTC (`17:00Z`) etkinlik saatleri `Europe/Istanbul` saat dilimine normalize edildi; sorgu `timeZone=Europe/Istanbul`, `singleEvents=true`, `orderBy=startTime` kullanıyor.
- Gerçek Calendar doğrulaması geçti: `NOVA ASİSTAN — Özel Takvim`, 8 Ekim 2026 20:00–22:00, `Sezon Açılış Konseri — Bursa Bölge Devlet Senfoni Orkestrası`, Merinos AKKM Osmangazi Salonu.
- Gerçek Sheets doğrulaması geçti: `NOVA İş Merkezi` içinde İşler 4, Projeler 6, Rutinler 15 satır okunabildi.
- Bağımsız kritik retest: backend 4/4 ve Ayarlar Google doğrulama akışı %100 geçti (`iteration_2.json`).
- Gerçek Drive doğrulaması geçti: `NOVA ASİSTAN` klasörüne erişildi; klasörde çekirdek doküman ve `NOVA İş Merkezi` dosyası görüldü.
- Gerçek Docs doğrulaması geçti: `NOVA ASİSTAN — Çekirdek Kurallar ve Rutinler` belgesinden içerik ve başlıklar okundu (`AMAÇ`, `TEMEL DAVRANIŞ`, `ANA ALANLAR`, `SABİT RUTİNLER`).
- Ayarlar > Gerçek Veriyi Doğrula ekranı Calendar, Sheets, Drive ve Docs sonuçlarını gösteriyor; mobil bildirim taşması düzeltildi.
- Bağımsız Drive/Docs retest: backend 7/7 ve masaüstü/mobil Ayarlar akışı %100 geçti (`iteration_3.json`), mocked API yok.

## Conversation Intelligence Update (2026-10-08)
- Türkçe tarih çözümleyici eklendi (`dateparser` + kesin gün/ay/hafta günü çözümü): bugün, yarın, `11 Ekim`, `25 Ekim`, `gelecek cumartesi` gibi ifadeler Europe/Istanbul referansında çözümleniyor.
- Tarih soruları cache yerine `NOVA ASİSTAN — Özel Takvim` üzerinde istenen günün 00:00–24:00 gerçek zamanlı Calendar sorgusunu çalıştırıyor.
- Haftalık öncelik motoru takvim etkinliği yakınlığı, son tarih, seyahat, bilet/mekân bağımlılıkları ve proje durumunu birlikte değerlendiriyor.
- Günlük/haftalık cevaplara Projeler sekmesindeki aktif ve bekleyen Bora AI Stüdyo bağlamı eklendi; Grup Karadüş klibi ve Kadına Şiddet serisi gerçek veriden aktarılıyor.
- Komagene haftalık rutinleri haftanın geçmiş kısmı, bugün ve kalan işler olarak ayrılıyor; yalnız aktif Sheet rutinleri kullanılıyor.
- Tüm yeni konuşma yüzeylerinde hitap `Bora`; eski görünür `Bora Bey` mesajları ekranda yeni hitaba normalize ediliyor.
- `marin`, `shimmer` ve `nova` aynı Türkçe metin, stil talimatı ve speed `1.09` ile tek-paragraf TTS isteklerinde yeniden karşılaştırıldı.
- Kullanıcının marin ritim geri bildirimi sonrası alternatifler arasında `nova` (8.0/10) `shimmer`dan (7.0/10) daha doğal bulundu; final primary voice `nova`, fallback `marin` olarak ayarlandı.
- Production TTS speed `1.09`; doğal İstanbul Türkçesi, 20'lerin sonu/30'ların başı, orta perde, sakin-akıcı kadın yönetici asistanı talimatını kullanıyor.
- TTS metni cümlelere bölünmüyor; paragraf tek `audio.speech.create` çağrısında üretiliyor. Satır sonu, uzun tire, noktalı virgül ve yinelenen noktalama yapay duraklamaları azaltmak için normalize ediliyor.
- Primary `nova` hata verirse aynı tam paragraf/talimat/hızla yalnızca bir kez `marin` fallback deneniyor.
- Nihai gerçek endpoint `nova` örneği kadın-profesyonel asistan hissinde 9/10, genel doğallıkta 8.1/10 değerlendirildi.
- Bağımsız gerçek endpoint, single-request ve fallback sözleşme testleri 16/16 geçti (`iteration_10.json`); production API mocked değil.
- Zorunlu bağımsız gerçek veri regresyonu backend 8/8 ve frontend masaüstü/mobil %100 geçti (`iteration_4.json`); mocked API yok.
- Transient 90 saniye Google gecikmesi için yalnız calendar source id/summary 300 saniye ve Sheets 120 saniye TTL cachelendi; Calendar `events.list` içerikleri her tarih sorgusunda canlı kalıyor.
- Connect callback ve disconnect sonrası kullanıcı cache'i temizleniyor; bağımsız performans retesti 8/8 ve 4.42 saniyede geçti (`iteration_5.json`).

## Unified Voice/Text Data Routing (2026-10-08)
- Yazılı ChatPanel ve PushToTalk artık aynı `POST /api/chat` → `build_chat_package` → ortak intent service katmanını kullanıyor; mesaj kaydında `source=text|voice` tutuluyor.
- Ortak servisler: `service_briefing`, `service_today_schedule`, `service_pending_tasks`, `service_weekly_priorities`, `service_calendar_date_query`.
- `briefing`, `today_schedule`, `pending_tasks`, `weekly_priorities` ve tarih sorguları RapidFuzz tabanlı Türkçe semantik/fuzzy intent eşleştirmesine bağlandı.
- Desteklenen varyasyonlar: bugün/bugünkü program, bugün ne var, günün programı, briefing/brifing/günün özeti, bekleyen işler/görevler; tipik Whisper hataları anlamı koruyor.
- Ana ekran `GET /api/briefing/today` ve sesli brifing aynı deterministik gerçek veri servisinin birebir sonucunu kullanıyor.
- Calendar ve Sheets bağımsız sorgulanıyor; kaynak hatasında yanlış biçimde “yok” denmiyor, iki kaynak da başarısızsa gerçek Docs fallback deneniyor.
- Gerçek TTS → Whisper STT → chat E2E testinde üç zorunlu komut doğru intent ve gerçek Google verileriyle geçti: 8 Ekim konseri, Bora AI Stüdyo bağlamı ve 3 bekleyen Sheet işi.
- Brifing açık `8 Ekim` tarih etiketi içeriyor; masaüstü/mobil PushToTalk test kimlikleri benzersiz.
- Zorunlu bağımsız retest backend 15/15, frontend %100 geçti (`iteration_7.json`); mocked API yok.

## NOVA Official Portrait Identity (2026-10-08)
- Kullanıcının son yüklediği `Altın Işıklı Şık Yönetici Portresi nova` resmi NOVA'nın tek resmi temsil görseli olarak bağlandı.
- Kaynak PNG (1122×1402) generative değişiklik yapılmadan WebP'ye optimize edildi: `/frontend/public/nova-portrait.webp` (154604 bayt).
- Masaüstü sağ NOVA panelinde eski büyük altın kürenin yerine ince siyah-altın çerçeveli 3:4 portre kullanılıyor; yüz/üst gövde odağı `50% 40%`.
- Login ekranındaki eski turuncu orb tamamen kaldırıldı; resmi portre 3:4 oran, altın halo ve `Hazır` durumuyla giriş kimliğine bağlandı.
- Bugün ekranındaki Günün Brifingi alanındaki eski turuncu orb kaldırıldı; ortak `NovaPortrait` bileşeni idle/listening/thinking/speaking durumlarıyla kullanılıyor.
- Ayarlar sayfasına büyük 3:4 `Resmi Asistan Kimliği` bölümü eklendi; minimum crop ile yüz, saç ve üst gövde korunuyor.
- Mobil alt çubukta aynı görselin küçük yuvarlak, yüz merkezli (`50% 38%`) avatarı kullanılıyor.
- Hazır, Dinliyor, Düşünüyor ve Konuşuyor state'leri portre çerçevesindeki sakin/pulse/ring/yumuşak animasyonlarla korunuyor.
- Bağımsız UI testi: frontend build, asset serve, masaüstü 1920×800 ve mobil 390×844 ana ekran/Ayarlar görünümleri %100 geçti; yatay taşma ve crop bozulması yok (`iteration_9.json`).
- Login ve Bugün portre düzeltmesinin nihai doğrulaması masaüstü 1920×800 ve mobil 390×844 smoke testlerinde geçti: görseller yüklendi, çerçeveler tam 3:4 oranında kaldı ve yatay taşma oluşmadı.
- Zorunlu bağımsız frontend retesti %100 geçti; eski orb DOM/UI kalıntısı bulunmadı, canlı Google Workspace snapshot bağlantısı doğrulandı ve mocked akış kullanılmadı (`iteration_13.json`).

## Shared Google Workspace Page Data Layer (2026-10-08)
- Menü sayfalarının local Mongo `/tasks` ve `/events` bağımlılığı kaldırıldı; chat ve tüm ekranlar aynı `/backend/workspace_data.py` kaynağını kullanıyor.
- `GET /api/workspace/snapshot` Calendar ve Sheets verilerini bir kez okuyup normalize ediyor: bugün, yarın, hafta, takvim, bekleyen işler, öncelikler ve bağlam görünümleri tek sözleşmeden dönüyor.
- Frontend `WorkspaceDataProvider`, authenticated Layout üzerinde tek snapshot'ı paylaşarak SPA rota değişimlerinde sayfa bazlı veri mantığını kaldırıyor.
- Bugün/Yarın/Bu Hafta/Takvim `NOVA ASİSTAN — Özel Takvim`; Bekleyen İşler/Öncelikler `NOVA İş Merkezi` İşler+Projeler kaynaklarına geçti.
- Komagene aktif Rutinler; Tiyatral Nikâh gerçek Calendar nikâhları + ilgili bekleyen İşler; Bora AI Stüdyo aktif/bekleyen Projeler verilerini gösteriyor.
- Kişisel yalnız gerçek Google Workspace kategorili kayıtlarını gösteriyor; Hızlı Notlar local CRUD olarak korundu.
- Gerçek veri doğrulaması: 8 Ekim 20:00 konseri Bugün/Takvim/Bu Hafta; 11 Ekim Villa Verde Bu Hafta/Tiyatral; Alanya-Antalya işleri; Komagene sipariş/sevkiyat rutinleri; Grup Karadüş ve Kadına Şiddet projeleri tüm ilgili rotalarda görüldü.
- Bağımsız backend snapshot testi ve masaüstü 1920×800/mobil 390×844 SPA testi %100 geçti (`iteration_11.json`); sayfalarda `/api/tasks` veya `/api/events` isteği yok, production API mocked değil.
- Son regresyon: backend 46/46, frontend production build başarılı; geçici test session kalıntısı yok.

## Security Hardening and PASS Re-audit (2026-10-08)
- CORS wildcard kaldırıldı; preview, FRONTEND_URL production origin ve `novaasistan.com`/`www` exact allowlist kullanıyor. Beklenmeyen Origin 403; credentialed wildcard reflection yok.
- Session cookie HttpOnly + Secure + SameSite=Lax + Path=/ + 7 gün; `SESSION_SECRET` güçlü rastgele değerle döndürüldü, Google token encryption key korunarak mevcut bağlantı bozulmadı.
- Signed, session-bound HMAC CSRF token `/api/auth/csrf` ile tüm authenticated POST/PUT/PATCH/DELETE isteklerinde zorunlu. Origin/Referer kontrolü ve frontend Axios otomatik CSRF akışı eklendi.
- Google connect GET'ten CSRF korumalı POST'a geçirildi; OAuth callback standard PKCE + tek kullanımlık süreli state korumasını sürdürüyor.
- Ham provider exception mesajları istemci/loglardan kaldırıldı; sabit güvenli mesajlar ve yalnız exception type logging kullanılıyor. OAuth callback code/state/token redaksiyonu korundu; geçmiş loglar sanitize edildi.
- Chat 30/dk, TTS ve STT 20/dk signed-session sliding-window rate limit; 429 + Retry-After eklendi.
- Backend ve frontend için CSP, HSTS, nosniff, Referrer-Policy, Permissions-Policy, X-Frame-Options/frame-ancestors ve CORP başlıkları eklendi; API cevapları no-store.
- `/api/google/verify` admin-only; env dosyaları gitignore altında ve third-party base URL'ler env kaynaklı.
- Zorunlu testing agent: security 9/9, full + bağımsız kontroller toplam 62/62; browser CSRF negative/positive, cookie, CORS, redaksiyon, rate limit, headers ve production build geçti (`iteration_12.json`).
- Security Audit re-run verdict: `PASS — NO MATERIAL FUNCTIONAL ISSUES FOUND`; güvenlik açısından READY.
- P3 bakım: çok-worker ortamında distributed rate-limit store; production CSP unsafe-inline azaltma; production ingress CORS davranışını yayın sonrası runtime doğrulama.

## Single-User Production Authorization Lock (2026-10-08)
- Emergent-managed Google session exchange artık backend'de normalize edilmiş ve doğrulanmış email kimliğini kontrol ediyor; yalnız `yapayzekasanatcisi@gmail.com` kabul ediliyor.
- Farklı hesaplar local user/session/cookie veya Google token kaydı oluşmadan HTTP 403 ile durduruluyor.
- Yetkisiz yanıt metni ürün genelinde sabitlendi: `NOVA, Yapay Zeka Sanatçısı Bora ÜNSAL’a özel kişisel asistandır. Yetkisiz erişim reddedildi.`
- Merkezi `current_user` authorization katmanı eski yetkisiz signed sessionları 403 ile reddedip session kaydını siliyor; Chat, TTS, STT, Workspace snapshot, Calendar, Sheets, Drive ve Docs provider/model çağrısından önce duruyor.
- Google Workspace OAuth callback, state'e bağlı kullanıcı allowlist dışında ise token exchange ve storage başlamadan 403 dönüyor.
- Login ekranı backend 403 detayını `login-access-denied-alert` içinde masaüstü ve mobilde gösteriyor; yatay taşma yok.
- Mevcut `google_tokens` sahipliği doğrulandı: tek token owner izinli hesaba bağlı; token değerleri okunmadı, yazdırılmadı veya değiştirilmedi.
- Hedefli auth + güvenlik regresyonu bağımsız doğrulamada 21/21 geçti; frontend production build başarılı (`iteration_14.json`). Son self-test 5/5 geçti ve geçici auth test kayıtları temizlendi.
- Production bypass sonrası allowlist email kodda sabitlendi, merkezi `SingleUserAuthorizationMiddleware` tüm private `/api` yüzeylerine eklendi ve `AUTH_SESSION_VERSION=2` ile eski cookie/session taşıma yolu kapatıldı.
- Unauthorized `/api/auth/session` artık hiçbir user/session/cookie/token oluşturmadan 403 dönüyor ve tarayıcıdaki önceki `nova_session` cookie'sini expire ediyor; OAuth callback sırasında eski Bora oturumu frontend state'inden taşınmıyor.
- Production startup enforcement çalıştı: 11 eski session ve 4 yetkisiz user temizlendi; izinli hesaba bağlı tek Google token kaydı korundu.
- Güncel production revision `novaasistan.com` üzerinde doğrulandı; Login ekranında eski orb kaldırıldı, resmi 3:4 portre masaüstü 230×306.66 ve mobil 190×253.33 ölçülerinde yüklendi, orb sayısı 0 ve yatay taşma yok.
- Gerçek production OAuth testi kullanıcı tarafından tamamlandı: farklı gerçek Gmail hesabı tam özel 403 mesajıyla reddedildi ve NOVA açılmadı; `yapayzekasanatcisi@gmail.com` başarıyla giriş yaptı ve gerçek NOVA verileri açıldı.
- Production anonim kontrollerinde `/api/auth/me`, Workspace, Google Drive, Chat, TTS ve STT cookie olmadan 401 ile durdu; kod/preview bağımsız hardening regresyonu 8/8 geçti (`iteration_15.json`).
- Son read-only production audit aktif run `54614e7e-ea06-457c-a231-a3e5153ffa9b` üzerinde geçti: users yalnız izinli hesap, `google_tokens` yalnız izinli owner, unauthorized session exchange sonrası hiçbir user/session/token/state artığı yok ve korumalı endpoint başarısı yok.
- Audit anında logout/restart sonrası `sessions` koleksiyonu boştu; bu nedenle canlı bir dokümanda `auth_version=2` alanı post-hoc görülemedi. Version 2 yazımı kodda ve bağımsız testlerde doğrulandı; production gerçek login sonrası private istekler 200 geçti.

## NOVA Core Intelligence V2 (2026-10-09, deploy approval pending)
- Deterministik Personal Memory eklendi: Bora, Tuğba, Atakan, anne, Tolga doğum günleri; özel günler; yemek/çorba, mayonez, araç ve seyahat tercihleri.
- Sebze yemeği kesin kuralı ile personal unknown fallback modelsiz çalışıyor; kayıtlı olmayan kişisel bilgi `Bu bilgi bende kayıtlı değil, Bora.` ile duruyor.
- Router önceliği Conversation Context → Personal Memory → Workspace → Live Web → General LLM → Unknown olarak ayrıldı; RapidFuzz threshold/margin yükseltildi ve kısa-token false-positive yolu kapatıldı.
- Personal Memory ve Workspace sorguları model çağrısı yapmıyor; general knowledge mevcut GPT-4o-mini üzerinden yalnız gerektiğinde çalışıyor.
- Live Web, kullanıcı onayıyla Gemini 2.5 Flash + Google Search grounding kullanıyor. Annotation, grounding metadata, nested raw ve content URL formatları normalize ediliyor; citation yoksa tek düşük maliyetli retry, sonra dürüst web-failure uygulanıyor.
- Travel query expansion Bursa–İstanbul köprü/feribot ve güncel ücret/sefer/süre araştırmasını; tarihli Alanya sorgularında Calendar/Workspace bağlamını ayrı deterministik katmanda birleştiriyor.
- Conversation context `user_id + conversation_id` bazında tutuluyor; `Peki kaçta?` aynı etkinlik context'inden modelsiz cevaplanıyor. Text ve voice aynı `/api/chat` pipeline'ını kullanıyor; Whisper `Tuba` varyantı Tuğba olarak kabul ediliyor.
- Haftalık öncelik motoru geçmiş etkinlikleri ve aksiyon içermeyen sosyal etkinlikleri mekanik iş olarak sıralamıyor.
- Final test: unit/router 20/20 PASS. Bağımsız gerçek acceptance 19/21 sonrası iki citation sorunu düzeltildi; Alanya ve İstanbul hedefli gerçek provider retestleri PASS. Zorunlu 21 akışın tamamı final kodda PASS; voice 3/3, MOCKED API yok.
- Production deploy kullanıcı seçimi gereği yapılmadı; açık onay bekleniyor.

## NOVA Final Hotfix (2026-10-09, deploy approval pending)
- Router ana niyet önceliği düzeltildi: Travel, Hotel, Restaurant, Cinema, Event ve Leisure intentleri `yarın`, `bu akşam`, `bu hafta sonu` ifadelerinden önce sınıflandırılıyor; bu ifadeler tek başına Workspace/Routine tetiklemiyor.
- Gemini Google Search kategori bazlı resmi kaynak matrisi aldı: Obilet/resmi firma, Pegasus/THY/AJet ayrımı, TCDD, İDO/BUDO, Hotels.com/resmi otel, Cinetime ÖzdilekPark, resmi mekan/etkinlik, Yemeksepeti ve alışveriş kaynak öncelikleri.
- Personal Memory karar filtresi sessiz çalışıyor; restoran/sinema/otel/travel tercihleri kullanıcı istemedikçe cevapta profil listesi olarak tekrarlanmıyor. Evlilik yıldönümü 11 Ocak olarak eklendi.
- Canlı sonuçlar yalnız doğrulanmış citation ile kabul ediliyor; placeholder mekan/sefer/fiyat yasak. Doğrulanamazsa `Bu bilgiyi canlı kaynaktan doğrulayamadım, Bora.` yanıtı veriliyor.
- Web ana cevabından raw URL, markdown citation ve kaynak bölümü temizleniyor; kaynaklar Chat UI'da ayrı tıklanabilir bölümde tutuluyor.
- Conversation context hotel/restaurant/cinema/travel/web intentini ve kaynaklarını `user_id + conversation_id` bazında koruyor; Calendar saat follow-up modelsiz devam ediyor.
- TTS kaynak listesi, URL, domain ve citation okumuyor; `20:00` → `saat yirmi`, `19:30` → `saat on dokuz otuz` normalizasyonu uygulanıyor.
- Mobile ChatPanel `min-w-0`, `overflow-x-hidden`, `overflow-wrap:anywhere` ve kaynak `break-all` ile düzeltildi; uzun cevapta input görünür, içerik dikey scroll ve yatay taşma yok. Desktop etkilenmedi.
- Hedefli self-test: hotfix unit/router 14/14; real web/voice/context 12/12; mobile+desktop responsive PASS. Bağımsız hedefli test iteration_17: unit 14/14 + son kritik real 3/3 + responsive PASS. Full regression kredi tasarrufu gereği tekrarlanmadı; MOCKED API yok.
- Production deploy yapılmadı; kullanıcı açık onayı bekleniyor.

## Backlog (next phases)
### P0
- Gmail entegrasyonu

### P1
- NOVA'nın notu/işi otomatik ayırt edip doğru koleksiyona kaydetmesi (function calling)
- Akşam raporu endpoint
- Proaktif bildirimler (web push / telegram)
- Komagene rutin otomasyonu (Salı/Cuma sipariş hatırlatıcısı otomatik oluştursun)
- Abonelik takibi
- Chat yanıtlarını SSE streaming ile kademeli göstermek

### P2
- PWA manifesto + offline önbellek
- Avatar yükleme (NOVA karakteri görsel değiştirme)
- Dudak senkronlu avatar (ileri sürüm)
- Türkçe için daha doğal ses (ElevenLabs opsiyonu)
