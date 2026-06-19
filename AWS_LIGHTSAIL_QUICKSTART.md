# AWS Lightsail 처음 배포 가이드 (초보자용)

대상: `erp.well-green.com`로 사내 ERP 띄우기
리전: `ap-northeast-2` (서울)
도메인: 카페24 호스팅에 A 레코드 추가

전체 7페이즈, 예상 소요: 첫 배포는 2~3시간 (DNS 전파 대기 포함).

```
페이즈 1: Lightsail 인스턴스 만들기            (콘솔, 15분)
페이즈 2: 고정 IP 할당                         (콘솔, 5분)
페이즈 3: 카페24에서 서브도메인 A 레코드 추가   (카페24, 10분 + 전파 대기)
페이즈 4: SSH 접속 + Docker 설치               (터미널, 15분)
페이즈 5: 코드 클론 + 환경변수 설정            (터미널, 20분)
페이즈 6: 첫 기동 + HTTPS 자동 발급 확인       (터미널, 10분)
페이즈 7: S3 백업 버킷 + IAM + rclone 연결     (콘솔+터미널, 30분)
```

---

## 페이즈 1 — Lightsail 인스턴스 만들기

1. AWS 콘솔 로그인 → 오른쪽 위 리전을 **서울 (ap-northeast-2)** 로 변경
2. 검색창에 **Lightsail** 입력 → 첫 결과 클릭
3. **인스턴스 생성** 클릭
4. 다음과 같이 선택:

   | 항목 | 값 |
   | --- | --- |
   | 인스턴스 위치 | 서울, Zone A (ap-northeast-2a) |
   | 플랫폼 | Linux/Unix |
   | 블루프린트 | OS 전용 → **Ubuntu 22.04 LTS** |
   | 인스턴스 플랜 | **$20/월** (2 vCPU / 4 GB RAM / 80 GB SSD) |
   | 인스턴스 이름 | `erp-prod` |

5. **인스턴스 생성** 클릭
6. 약 1~2분 후 상태가 **Running**으로 변하면 완료

### 방화벽 (네트워킹) 열기

인스턴스를 클릭 → 상단 **네트워킹** 탭 → IPv4 방화벽:

| 애플리케이션 | 프로토콜 | 포트 |
| --- | --- | --- |
| SSH | TCP | 22 (기본) |
| HTTP | TCP | 80 (추가) |
| HTTPS | TCP | 443 (추가) |

80/443 두 개를 **+ 규칙 추가**로 열어주세요. Postgres(5432)는 **절대 열지 마세요**.

---

## 페이즈 2 — 고정 IP 할당

인스턴스 IP는 재시작 시 바뀝니다. 고정 IP로 묶어주세요.

1. Lightsail 좌측 **네트워킹** → **고정 IP 생성**
2. 리전: 서울, 인스턴스: `erp-prod` 선택
3. 이름: `erp-prod-ip`
4. **생성** 클릭
5. 표시된 IP(예: `13.124.xxx.xxx`)를 메모장에 복사 → **이걸 카페24에 등록**

> 💡 고정 IP는 인스턴스에 연결돼 있는 한 무료입니다. 인스턴스에서 떼면 시간당 과금되니, 안 쓸 거면 IP도 삭제하세요.

---

## 페이즈 3 — 카페24에서 서브도메인 A 레코드 추가

1. 카페24 호스팅 관리자 로그인
2. **나의서비스관리** → **도메인 관리** → `well-green.com` 선택
3. **DNS 관리** (또는 **호스트 IP 관리**) 메뉴 진입
4. **레코드 추가**:

   | 호스트 (서브도메인) | 타입 | 값 (IP) | TTL |
   | --- | --- | --- | --- |
   | `erp` | A | `<페이즈 2의 고정 IP>` | 600 (10분) 또는 기본값 |

5. 저장

### DNS 전파 확인

터미널에서:

```bash
dig +short erp.well-green.com
# 또는 윈도우: nslookup erp.well-green.com
```

→ 페이즈 2의 IP가 뜨면 OK. 5~30분 걸릴 수 있고, 카페24는 보통 빠른 편 (5분 내외).

---

## 페이즈 4 — SSH 접속 + Docker 설치

### SSH 키 다운로드

1. Lightsail 좌측 **계정** → **SSH 키** 탭
2. 서울 리전의 **기본 키** → **다운로드** → `LightsailDefaultKey-ap-northeast-2.pem` 저장
3. 권한 조정 (Mac/Linux):

   ```bash
   chmod 600 ~/Downloads/LightsailDefaultKey-ap-northeast-2.pem
   ```

### SSH 접속

```bash
ssh -i ~/Downloads/LightsailDefaultKey-ap-northeast-2.pem ubuntu@erp.well-green.com
```

> Windows는 PuTTY 또는 PowerShell의 `ssh` 명령 사용.
> Lightsail 콘솔의 "Connect using SSH" 버튼으로 브라우저 SSH도 가능합니다 (키 다운로드 불필요).

### Docker / Compose 설치

```bash
# 시스템 업데이트
sudo apt update && sudo apt -y upgrade

# Docker 공식 설치 스크립트
curl -fsSL https://get.docker.com | sudo sh

# 현재 사용자가 sudo 없이 docker 실행 가능하게
sudo usermod -aG docker ubuntu

# git, 자주 쓰는 유틸
sudo apt -y install git ufw fail2ban

# 재로그인해서 그룹 권한 적용
exit
```

다시 SSH 접속:

```bash
ssh -i ~/Downloads/LightsailDefaultKey-ap-northeast-2.pem ubuntu@erp.well-green.com
docker --version
docker compose version
```

두 버전이 모두 뜨면 OK.

---

## 페이즈 5 — 코드 클론 + 환경변수 설정

```bash
# 코드 받기 (현재 작업 브랜치 사용)
git clone -b claude/new-session-PLMnC https://github.com/sug5264-bit/erp-system.git
cd erp-system

# 시크릿 자동 생성
./scripts/gen-secrets.sh > .env

# 사내 운영용 환경값 추가
cat >> .env <<'EOF'
PUBLIC_DOMAIN=erp.well-green.com
LETSENCRYPT_EMAIL=it@well-green.com
NEXT_PUBLIC_API_BASE=https://erp.well-green.com
CORS_ORIGINS=["https://erp.well-green.com"]
SEED_DEMO_USERS=0
RATE_LIMIT_ENABLED=true
ENVIRONMENT=production
EOF

# 내용 확인
cat .env
```

> ⚠️ `LETSENCRYPT_EMAIL`은 실제 받는 이메일로 바꿔주세요. 인증서 만료 임박 시 알림이 옵니다.

---

## 페이즈 6 — 첫 기동 + HTTPS 자동 발급 확인

```bash
# 프로덕션 overlay와 함께 기동
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 5~10분 정도 첫 빌드/마이그레이션 진행
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f
```

로그에서 다음을 확인:

| 컴포넌트 | 확인 메시지 |
| --- | --- |
| `db` | `database system is ready to accept connections` |
| `backend` | `Application startup complete` + `Uvicorn running` |
| `proxy` (Caddy) | `certificate obtained successfully` (Let's Encrypt 발급 성공) |
| `frontend` | `ready - started server` |

브라우저에서 `https://erp.well-green.com` 접속 → 로그인 화면이 뜨면 성공.

### 첫 admin 만들기

```bash
docker compose exec backend python -m scripts.create_admin \
  --email it@well-green.com \
  --password "$(openssl rand -base64 16)"
```

출력된 비밀번호를 안전하게 보관. 로그인 후 즉시:

1. **2FA 활성화** (사용자 메뉴 → 2FA 설정)
2. 비밀번호 변경

---

## 페이즈 7 — S3 백업 버킷 + IAM + rclone

### S3 버킷 만들기

1. AWS 콘솔에서 **S3** 검색
2. **버킷 만들기**:
   - 이름: `wellgreen-erp-backups` (전 세계 유일해야 함)
   - 리전: **서울 (ap-northeast-2)**
   - 모든 퍼블릭 액세스 차단: **체크 유지** (기본값)
   - 버킷 버전 관리: **활성화** (실수 복구용)
   - 기본 암호화: **SSE-S3** (기본)
3. 생성

### IAM 사용자 만들기 (백업 전용)

1. **IAM** → **사용자** → **사용자 추가**
2. 이름: `erp-backup-uploader`
3. **다음** → 권한 옵션:
   - **직접 정책 연결** → **정책 생성**
   - JSON 탭:
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [{
         "Effect": "Allow",
         "Action": ["s3:PutObject", "s3:GetObject", "s3:ListBucket", "s3:DeleteObject"],
         "Resource": [
           "arn:aws:s3:::wellgreen-erp-backups",
           "arn:aws:s3:::wellgreen-erp-backups/*"
         ]
       }]
     }
     ```
   - 정책 이름: `erp-backup-s3-rw` → 생성
4. 사용자에 정책 연결 → 사용자 생성
5. 사용자 클릭 → **보안 자격 증명** 탭 → **액세스 키 만들기** → "기타" 선택
6. `Access key ID`와 `Secret access key` 메모 (한 번만 표시됨!)

### rclone 설정

서버에서:

```bash
cd ~/erp-system

# 템플릿 복사
cp deploy/rclone.conf.example deploy/rclone.conf

# 편집
nano deploy/rclone.conf
```

다음 [s3] 섹션만 남기고 나머지는 지우거나 주석 처리:

```ini
[s3]
type = s3
provider = AWS
access_key_id = AKIA...        # 위에서 받은 값
secret_access_key = ...        # 위에서 받은 값
region = ap-northeast-2
storage_class = STANDARD_IA
```

저장 (Ctrl+O → Enter → Ctrl+X).

```bash
# .env에 백업 대상 추가
echo 'BACKUP_REMOTE_TARGET=s3:wellgreen-erp-backups' >> .env
echo 'BACKUP_RETENTION_DAYS=30' >> .env

# backup 컨테이너만 재시작
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d backup

# 즉시 백업 한 번 실행 (테스트)
docker compose exec backup /usr/local/bin/backup.sh
```

마지막 명령이 `backup ok` 로 끝나면 성공. S3 콘솔에서 버킷에 `erp_<timestamp>.sql.gz` 파일이 보이는지 확인.

---

## 운영 체크리스트 (페이즈 7 이후)

배포 직후:
- [ ] `https://erp.well-green.com` 접속 OK
- [ ] HTTPS 자물쇠 표시 (인증서 자동 발급 완료)
- [ ] 첫 admin 2FA 활성화
- [ ] S3에 백업 파일 1개 도달
- [ ] 재택에서 핸드폰으로 접속 테스트

월 1회:
- [ ] AWS 청구서 확인 (Lightsail $20 + S3 $1 미만 예상)
- [ ] `docker compose logs proxy | grep -i error` (인증서 갱신 문제 없는지)
- [ ] S3 백업 파일 무결성 점검 (`rclone ls s3:wellgreen-erp-backups`)

분기 1회:
- [ ] OS 패치: `sudo apt update && sudo apt -y upgrade`
- [ ] Docker 이미지 재빌드: `docker compose build --pull && docker compose up -d`
- [ ] 복구 리허설: 별도 Lightsail 인스턴스에 dump 복원해보기

---

## AWS 이행 사다리 (1~2년 후)

언제 다음 단계로 갈지:

| 신호 | 다음 단계 |
| --- | --- |
| CPU 평균 > 60% | Lightsail $40 플랜으로 업그레이드 (4 vCPU / 8 GB) |
| DB 크기 > 30 GB | **RDS Postgres**로 DB만 분리 (백엔드는 Lightsail 유지) |
| 사용자 > 100명 | 백엔드를 **ECS Fargate**로 이행, ALB 앞에 두기 |
| 다국가 / 다지점 | CloudFront + S3 정적 호스팅 추가 |

지금 만든 모든 구성은 위 단계로 자연스럽게 이행됩니다 — DB는 pg_dump로 RDS에 복원, 백엔드 컨테이너는 같은 이미지를 ECR/ECS로, S3 버킷은 그대로 재사용.

---

## 트러블슈팅

**HTTPS가 안 뜨고 "connection refused"**
→ Lightsail 방화벽에서 443 포트가 열렸는지 확인.

**Caddy 로그에 `no such host` / `acme: error`**
→ DNS가 아직 전파 안 됨. `dig +short erp.well-green.com` 결과를 다시 확인하고 10분 더 기다리세요.

**`docker compose up` 중 OOM (메모리 부족)**
→ 첫 빌드가 무겁습니다. 스왑 추가:
```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**rclone 백업이 `403 Forbidden`**
→ IAM 정책의 버킷 이름이 정확한지, 액세스 키가 올바른지 확인.

문제가 생기면 로그와 함께 알려주세요 — 같이 디버그하면서 진행하면 됩니다.
