# WellGreen Mobile (Expo / React Native)

WellGreen ERP 백엔드를 사용하는 모바일 앱 스켈레톤.

## 기능 (PoC)
- 로그인 (이메일/비밀번호 → JWT, expo-secure-store에 저장)
- 대시보드 (직원·품목·재고부족·주문·총매출)
- 재고 목록
- 주문 목록

## 실행
```bash
cd mobile
npm install
npx expo start
```
- `app.json` 의 `extra.apiBase` 를 백엔드 URL로 변경하세요.
- 실제 기기에서 실행 시 PC의 LAN IP 로 변경 (예: `http://192.168.1.10:8000`).

## 추후 확장
- 카메라로 영수증 촬영 → `/api/ocr/receipt` 호출 (자동 품목 등록)
- 푸시 알림 (Expo Notifications + 백엔드 WebSocket)
- 오프라인 대기열 (재고 입출고 기록 저장 후 온라인 시 동기화)
