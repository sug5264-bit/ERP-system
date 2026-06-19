# 사내 배포 가이드 — 외부 접근 + 10~50명 + 외부 백업

이 문서는 다음 시나리오에 최적화되어 있습니다:

- **사용자**: 회사 직원만 (재택 포함)
- **접근**: 인터넷에서도 (재택 사원)
- **규모**: 10~50명
- **백업**: 일일 자동 + S3/NAS 등 외부 보관

배포 자체는 `DEPLOYMENT.md`의 **옵션 B**와 동일합니다. 여기서는 사내
운영에 특화된 추가 설정·강화를 정리합니다.

---

## 1. 기본 배포 (DEPLOYMENT.md 옵션 B 그대로)

```bash
# 1) 시크릿 생성
./scripts/gen-secrets.sh > .env

# 2) 사내 운영용 환경값 추가
cat >> .env <<'EOF'
PUBLIC_DOMAIN=erp.wellgreen.co.kr
LETSENCRYPT_EMAIL=it@wellgreen.co.kr
NEXT_PUBLIC_API_BASE=https://erp.wellgreen.co.kr
CORS_ORIGINS=["https://erp.wellgreen.co.kr"]
SEED_DEMO_USERS=0
RATE_LIMIT_ENABLED=true
EOF

# 3) 기동
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

DNS A 레코드 `erp.wellgreen.co.kr → <서버 공인 IP>` 설정 후, 80/443
포트 오픈하면 Caddy가 Let's Encrypt 인증서를 자동 발급합니다.

---

## 2. 외부 백업 자동화 (S3 / NAS)

### 2.1 백엔드 선택

`deploy/rclone.conf.example`에 5가지 백엔드 예시가 있습니다.

| 옵션 | 추천 시 | 월 비용 (50MB×30일 가정) |
| ---- | ------- | ------------------------ |
| AWS S3 Standard-IA | 안정성 + 검색 빈도 낮음 | ~$0.02 |
| BackBlaze B2 | 비용 최우선 | ~$0.003 |
| Synology NAS (SMB/SFTP) | 사내 NAS 이미 있음 | 0 |
| Google Cloud Storage | Workspace 계정 활용 | ~$0.02 |

### 2.2 설정

```bash
# 1) 예시를 복사
cp deploy/rclone.conf.example deploy/rclone.conf

# 2) 사용할 한 섹션만 주석 해제하고 자격 증명 채워 넣기
$EDITOR deploy/rclone.conf

# 3) .env에 어떤 remote로 보낼지 지정
echo 'BACKUP_REMOTE_TARGET=s3:wellgreen-erp-backups' >> .env

# 4) 재시작
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  up -d backup
```

### 2.3 동작

`backup` 컨테이너가 매 24시간:
1. `pg_dump … | gzip` → `/backups/erp_<timestamp>.sql.gz`
2. 로컬 14일 rotation (기본값, `BACKUP_RETENTION_DAYS`로 조정)
3. `BACKUP_REMOTE_TARGET` 설정되어 있으면 rclone으로 외부 업로드
4. 외부 업로드 실패해도 로컬 백업은 유지 (graceful)

수동 실행 / 즉시 백업:

```bash
docker compose exec backup /usr/local/bin/backup.sh
```

복구 (재해 리허설 권장):

```bash
# 외부에서 다시 받아오기
docker compose exec backup rclone copy s3:wellgreen-erp-backups/erp_20260513T030000Z.sql.gz /tmp/

# 복구
docker compose -f docker-compose.yml stop backend frontend proxy
./deploy/restore.sh deploy/backups/erp_20260513T030000Z.sql.gz
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 3. 사내 보안 권장 (재택 사원 대비)

### 3.1 첫 admin은 반드시 2FA 강제

```bash
# 1) 첫 admin으로 로그인 후 2FA 활성화
curl -X POST https://erp.wellgreen.co.kr/api/auth/2fa/setup \
  -H "Authorization: Bearer <access_token>"
# → QR로 표시되는 otpauth URL을 Google Authenticator/Authy로 등록

curl -X POST https://erp.wellgreen.co.kr/api/auth/2fa/enable \
  -H "Authorization: Bearer <access_token>" \
  -d '{"code":"123456"}'
```

### 3.2 Google Workspace SSO (선택)

회사가 Google Workspace를 쓴다면 사원 Gmail로 바로 로그인 시킬 수 있습니다.

```bash
# Google Cloud Console → OAuth client ID 발급 후 .env에 추가
cat >> .env <<'EOF'
GOOGLE_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxx
GOOGLE_REDIRECT_URI=https://erp.wellgreen.co.kr/api/auth/oauth/google/callback
OAUTH_DEFAULT_ROLE=staff
EOF

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d backend
```

이후 로그인 화면에 "Google로 로그인" 버튼이 자동 노출됩니다. **회사 도메인
사용자만 허용**하려면 Google Cloud Console의 OAuth consent screen에서
"Internal" (Workspace 한정) 설정을 사용하세요.

### 3.3 관리자 엔드포인트 IP 허용 (옵션)

`/admin/*` 페이지나 `/api/admin_ops/*` 등을 회사 IP만 허용하려면
`deploy/Caddyfile`에 다음 블록을 추가:

```caddyfile
{$PUBLIC_DOMAIN} {
    # ... 기존 설정 ...

    @admin path /admin/* /api/admin_ops/* /api/finance/journal-entries/*/void
    @company_ip remote_ip 211.123.45.0/24 2001:db8::/32  # 회사 게이트웨이 / VPN
    handle @admin {
        @denied not @company_ip
        respond @denied 403
        reverse_proxy backend:8000
    }
}
```

또는 모든 사용자에 강제 2FA를 적용하려면 `auth/router.py:login`에서
`if not user.totp_enabled: raise HTTPException(403, "2FA enrollment required")`
한 줄 추가하면 됩니다 (사이트 정책에 맞춰 결정).

### 3.4 Slack 위반 알림

운영 중 위험 이벤트 (HACCP 한계 초과, 승인 SLA 초과, 결재 거절 등):

```bash
echo 'SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T0XX/B0YY/zzz' >> .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d backend
```

### 3.5 Sentry 에러 추적

```bash
echo 'SENTRY_DSN=https://xxx@oXXX.ingest.sentry.io/YYY' >> .env
echo 'SENTRY_TRACES_SAMPLE_RATE=0.2' >> .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d backend
```

---

## 4. 50명 규모 튜닝값

`.env`에 다음 값 추가/변경:

```ini
# 동시 요청 = workers × threads. 2×4 = 8 동시 처리 가능 (기본)
# 50명이면 동시 활성 ~10명 정도라 기본값으로 충분. 여유 두려면:
GUNICORN_WORKERS=4
GUNICORN_THREADS=4
GUNICORN_TIMEOUT=60

# 스케줄러 — 10명 미만은 5분, 50명대는 그대로 5분도 무난
SCHEDULER_INTERVAL_MINUTES=5

# 백업 보관일 — 50명 규모면 1~2GB / 30일 = ~60GB 정도. NAS 여유에 맞춰
BACKUP_RETENTION_DAYS=30
```

리소스 권장:
- **VM**: 2 vCPU / 4GB RAM / 50GB SSD (Postgres + 이미지 포함)
- **확장 시점**: CPU 평균 60% 초과 또는 P95 응답 > 1s 면 vCPU 늘리기

모니터링은 `https://erp.wellgreen.co.kr/metrics`에 Prometheus 형식으로
이미 노출되어 있습니다.

---

## 5. 운영 체크리스트

배포 직후:

- [ ] DNS A 레코드 확인 (재택 사원 핸드폰에서도 접속 테스트)
- [ ] HTTPS 인증서 자동 발급 완료 (`docker compose logs proxy | grep -i obtained`)
- [ ] 첫 admin 계정 2FA 활성화
- [ ] `SEED_DEMO_USERS=0` 확인
- [ ] 백업이 외부 (S3/NAS)에 실제로 도착했는지 확인 (`rclone ls` 또는 콘솔)
- [ ] **복구 리허설 1회 수행** — 별도 VM에 dump 적용해서 잘 살아나는지

월 1회:

- [ ] 보관된 백업 무결성 점검 (`gunzip -t *.sql.gz`)
- [ ] Sentry 에러 트렌드 검토
- [ ] 사용자 권한 감사 (`/api/auth/users` + `/api/compliance/dashboard`)
- [ ] `pg_dump` 크기 추적해 디스크 압박 예측

분기 1회:

- [ ] OS 패치 + Docker 이미지 재빌드 (`docker compose build --pull`)
- [ ] Postgres 마이너 버전 업그레이드 (16.x → 16.y)
- [ ] 전체 복구 리허설 (시간 측정)
