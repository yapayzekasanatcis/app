# NOVA Tek Kullanıcı Authentication ve CSRF Test Akışı

## Production authorization policy
- İzin verilen Google hesabı: `yapayzekasanatcisi@gmail.com`
- Yetkisiz yanıt: HTTP 403
- Yanıt metni: `NOVA, Yapay Zeka Sanatçısı Bora ÜNSAL’a özel kişisel asistandır. Yetkisiz erişim reddedildi.`
- OAuth session exchange yalnız backend üzerinden yapılır.
- Yetkisiz hesap için local user/session/cookie veya Google token kaydı oluşturulmaz.
- Mevcut signed `nova_session`, HttpOnly + Secure + SameSite=Lax sözleşmesi korunur.

## Zorunlu testler
1. `/app/memory/test_credentials.md` dosyasını oku; environment secret, OAuth code veya Google token yazdırma.
2. İzinli email ile provider session-data yanıtı: `/api/auth/session` local session/cookie üretmeli.
3. Farklı email ile provider session-data yanıtı: `/api/auth/session` 403 dönmeli; user/session/token kaydı oluşmamalı.
4. İzinli olmayan kullanıcıya bağlı geçerli imzalı eski session: `/api/auth/me` ve tüm private/ücretli endpointler 403 dönmeli.
5. Cookie olmadan private endpointler 401 dönmeli.
6. Chat, TTS, STT ve Google Workspace endpointlerinde authorization, model/provider çağrısından önce çalışmalı.
7. İzinli kullanıcının mevcut `google_tokens` kaydı değişmemeli; yetkisiz kullanıcıya token kopyalanmamalı.

## Session ve CSRF testi
1. Geçici test user/session oluştur ve session ID değerini güncel `SESSION_SECRET` ile imzala.
2. İmzalı değeri yalnız `nova_session` cookie olarak gönder.
3. `Origin` değerini mevcut frontend origin ile birebir eşleştir.
4. Authenticated POST, PUT, PATCH ve DELETE öncesi `GET /api/auth/csrf` çağır ve `X-CSRF-Token` gönder.
5. Negatif testlerde provider/model çağrısını spy/mock ile engelle ve çağrılmadığını doğrula.
6. Test sonunda geçici users, sessions, notes, OAuth state ve test mesajlarını sil.
7. Gerçek kullanıcının şifreli Google token kaydını asla silme veya değiştirme.

## Browser testi
- `/giris` herkese açık kalır.
- İzinli signed session ile `/` dashboard açılır.
- Yetkisiz signed session ile protected içerik açılmaz ve private API 403 döner.