# NOVA ASİSTAN - PRD

## Original Problem Statement
Türkçe konuşan, gerçek bir özel sekreter gibi davranan kişisel yapay zekâ asistanı NOVA. Kullanıcı Bora'nın hayatını (Komagene işletme, Tiyatral Nikâh organizasyonları, Bora AI Stüdyo, kişisel yaşam, önemli tarihler, Tuğba) tek merkezden koordine eder. Google Calendar/Drive/Sheets/Gmail entegrasyonu aşamalı. OpenAI gpt-4o-mini + Whisper + TTS. Türkçe sesli ve yazılı iletişim. Düşük maliyet (hedef <1500 TL/ay).

## Architecture
- **Backend**: FastAPI + MongoDB (motor async) + Emergent Universal LLM Key
- **Auth**: Emergent-managed Google OAuth (session cookie `nova_session`, HttpOnly, signed with itsdangerous)
- **LLM**: `emergentintegrations.llm.chat.LlmChat` → OpenAI gpt-4o-mini
- **Voice**: OpenAI Whisper (STT) + OpenAI gpt-4o-mini-tts (TTS) via Emergent proxy
- **Frontend**: React 19 + React Router + Framer Motion + Shadcn UI + Tailwind
- **Theme**: Dark Warm Executive (Obsidian + Amber) — Cormorant Garamond serif + Plus Jakarta Sans

## User Personas
- **Bora** (sole user): İşletme sahibi, organizasyoncu, AI stüdyo yöneticisi. Günlük rutini karmaşık; tek merkezden kontrol ister.

## Core Requirements (static)
1. Türkçe UI/sesli yanıt
2. NOVA karakteri (sıcak, profesyonel, kısa cevap, "Bora Bey" hitabı)
3. Push-to-talk mikrofon + sesli dinleme
4. Günlük brifing (takvim + öncelikler + bekleyen işler birleşik)
5. Tasks (bağlama göre: kişisel/komagene/tiyatral-nikâh/bora-ai-studyo) + Öncelik işareti
6. Notlar, Takvim/Etkinlikler CRUD
7. Önemli tarih hatırlatıcıları (Tuğba 10 Kasım, Komagene %50 Çiğköfte 15'i, aile)
8. Low cost (<1500 TL/ay)
9. Güvenlik: onaysız ödeme/rezervasyon/mail gönderme/etkinlik silme YOK

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
- P0 blokajı: Çalışan preview ortamı `GOOGLE_CLIENT_SECRET` değerini Client ID ile aynı görüyor. Bu nedenle OAuth bilinçli olarak başlatılmıyor; gerçek Google consent/token ve veri testi henüz tamamlanmadı.

## Backlog (next phases)
### P0
- Preview çalışma ortamına doğru `GOOGLE_CLIENT_SECRET` değerinin yansımasını sağla.
- Kullanıcının Ayarlar > Google'ı Bağla akışında consent vermesini tamamla.
- Gerçek veri doğrulamasında 8 Ekim 2026 20:00 Bursa Bölge Devlet Senfoni Orkestrası etkinliğini doğrula.
- `NOVA İş Merkezi` İşler / Projeler / Rutinler sekmelerinin gerçek satır sayılarını doğrula.
- Google Drive/Docs (`NOVA ASİSTAN` klasörü ve çekirdek doküman) gerçek okuma testi.
- Gmail entegrasyonu

### P1
- NOVA'nın notu/işi otomatik ayırt edip doğru koleksiyona kaydetmesi (function calling)
- Akşam raporu endpoint
- Proaktif bildirimler (web push / telegram)
- Araştırma yetenekleri (otobüs/uçak/otel karşılaştırma)
- Komagene rutin otomasyonu (Salı/Cuma sipariş hatırlatıcısı otomatik oluştursun)
- Abonelik takibi

### P2
- PWA manifesto + offline önbellek
- Avatar yükleme (NOVA karakteri görsel değiştirme)
- Dudak senkronlu avatar (ileri sürüm)
- Türkçe için daha doğal ses (ElevenLabs opsiyonu)
