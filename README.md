# MiriZoom: Amazon Linux 서버 3대 + JCasC + Ansible

Ansible을 **Jenkins 서버에 설치하고 그 서버에서 처음부터 실행**합니다. 사용자 PC는 SSH 접속과 파일 전달에만 사용합니다. Ubuntu도 Linux이지만 이번 구성은 요청에 따라 **Amazon Linux 2023, x86_64**로 변경했습니다. Blue-Green은 포함하지 않습니다.

## 실행 위치

```text
PC → Jenkins EC2에 SSH 접속
       ├─ 호스트 Ansible: 최초 서버 설정 → Docker/Jenkins/JCasC 준비
       └─ Jenkins 컨테이너의 Ansible: 이후 App/Web 배포
```

Jenkins가 없는 첫 단계에서도 Jenkins EC2 호스트에는 Ansible을 설치할 수 있습니다. 호스트에서 Bootstrap을 실행하면 자기 서버는 로컬 연결로 설정하고 App/Web은 private IP로 SSH 접속합니다. 이후 CI/CD는 같은 서버의 Jenkins 컨테이너 안에서 실행합니다.

## 1. AWS 프리티어 확인

이번 실습 계정은 **2026년 8월 생성**이므로 2025년 7월 15일 이후 신규 계정 제도가 적용됩니다. 신규 계정의 무료 플랜은 가입 후 최대 6개월 또는 크레딧 소진 시점까지이며, 가입 크레딧 $100과 조건 충족 시 추가 최대 $100을 받을 수 있습니다. t3.micro와 t3.small은 대상 유형입니다. [AWS 프리티어 조건](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html)

아래 구성은 프리티어 **대상 유형**을 사용합니다. 실제 무료 범위는 AWS Billing의 **현재 플랜, Credits 잔액, 만료일**로 결정됩니다. EC2 3대를 계속 켜 두면 크레딧을 사용합니다. Paid plan에서는 크레딧을 초과한 사용에 요금이 발생할 수 있습니다. Free plan에서는 기간/크레딧 종료에 따라 이용이 제한됩니다. [AWS 무료 플랜 FAQ](https://aws.amazon.com/free/free-tier-faqs/)

| 서버 | 시작 유형 | 메모리 | gp3 디스크 예시 |
| --- | --- | --- | --- |
| Jenkins | t3.small | 2 GiB | 20 GiB |
| App | t3.small | 2 GiB | 15 GiB |
| Web | t3.micro | 1 GiB | 8 GiB |

사양은 [AWS T3 자료](https://aws.amazon.com/ec2/instance-types/t3/)를 참고합니다. Jenkins/App을 1 GiB로 줄이면 빌드와 FastAPI 실행이 불안정해질 수 있어 2 GiB로 시작합니다. 이 사양에서 모든 작업이 충분하다는 보장은 없으며, 실제 메모리와 디스크 사용량을 확인합니다.

이번 코드의 소형 서버 설정:

- Jenkins 실행 슬롯 1개와 heap 최대 512 MiB
- Gradle worker 1개, 병렬 빌드 해제, heap 최대 512 MiB
- Backend heap 최대 512 MiB
- 서버별 2 GiB Swap (메모리 부족 완충용이며 RAM을 대체하지 않음)
- Batch는 기본 비활성, 실습 작업은 순서대로 실행

EBS, Public IPv4, RDS도 크레딧을 사용할 수 있습니다. 초기 실습은 NAT Gateway와 ALB 없이 구성합니다. 실습 종료 시 EC2를 중지하고, 계속 보관하는 EBS와 RDS 등의 사용량도 Billing에서 확인합니다. 중지는 실행 중인 서버의 과금을 줄이지만 모든 리소스 비용이 없어지는 것은 아닙니다.

## 2. EC2 3대 생성

세 서버 모두 최신 **Amazon Linux 2023 AMI, x86_64**, 같은 리전·VPC, 공통 Key Pair를 선택합니다. T3의 CPU credit specification은 추가 CPU credit 과금을 피하도록 **Standard**로 선택합니다. 크레딧이 부족하면 빌드가 느려질 수 있습니다. [AWS Standard 모드](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-standard-mode.html) Amazon Linux 2와 ARM/Graviton은 이번 코드의 대상이 아닙니다. SSH 계정은 `ec2-user`입니다.

이름은 `mirizoom-jenkins`, `mirizoom-app`, `mirizoom-web`로 구분합니다. Jenkins와 Web의 public IP, 세 서버의 private IP를 기록합니다. App에도 public IP를 부여하면 별도 NAT 없이 패키지·이미지를 다운로드할 수 있습니다. 외부 접속 허용은 보안 그룹으로 제한합니다. public subnet과 Internet Gateway 경로, 기본 아웃바운드 허용이 필요합니다.

**Jenkins 서버만** 생성 화면의 Advanced details → User data에 `../jenkins-infra/user-data.sh` 전체 내용을 입력합니다. 이 스크립트는 Git, Python 3.11, 초기 설정용 Ansible을 `/opt/mirizoom-bootstrap`에 설치합니다. App/Web에는 입력하지 않습니다.

Amazon Linux 2023의 기본 Python 3.9는 유지하고, Ansible 실행용 Python 3.11을 별도로 설치합니다. 시스템 Python 심볼릭 링크를 변경하지 않습니다. [AWS Python 설명](https://docs.aws.amazon.com/linux/al2023/ug/python.html)

### 보안 그룹

| 대상 | 인바운드 | 허용 출발지 |
| --- | --- | --- |
| Jenkins | TCP 22 | 내 PC 공인 IP `/32` |
| App | TCP 22 | `jenkins-sg` |
| App | TCP 8080 | `web-sg` |
| Web | TCP 22 | `jenkins-sg` |
| Web | TCP 80 | 실습 공개 시 인터넷, 개인 확인만 하면 내 IP `/32` |
| RDS | TCP 3306 | `app-sg` |

Jenkins 8080과 FastAPI 8000을 외부에 열지 않습니다. 443은 인증서 준비 후 HTTPS 적용 시 추가합니다. RDS MySQL은 EC2 3대와 별도이며 DB 스키마와 필요한 데이터 복원은 이번 코드에서 수행하지 않습니다.

## 3. Jenkins 서버에서 준비

PC에서 Jenkins public IP에 SSH 접속합니다. 첫 접속 fingerprint는 AWS EC2 System Log의 `BEGIN SSH HOST KEY FINGERPRINTS`와 비교합니다. [AWS SSH 접속 조건](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/connection-prereqs-general.html)

```bash
ssh -i /absolute/path/mirizoom.pem ec2-user@JENKINS_PUBLIC_IP
```

User data 완료를 확인합니다.

```bash
sudo cloud-init status --wait
/opt/mirizoom-bootstrap/bin/ansible --version
```

Jenkins 서버의 `/home/ec2-user/KB_PTJ`에 `jenkins-infra`와 `deploy`를 형제 폴더로 배치합니다. GitHub에 변경된 파일을 먼저 반영한 다음, 각 저장소를 clone하는 방식으로 준비합니다. private 저장소는 GitHub 인증이 필요합니다.

```bash
mkdir -p /home/ec2-user/KB_PTJ
cd /home/ec2-user/KB_PTJ
git clone --branch feature_jenkins_ansible_cicd https://github.com/KB-IT-s-your-life-PJT-23-4/jenkins-infra.git
git clone --branch feature_jenkins_ansible_cicd https://github.com/KB-IT-s-your-life-PJT-23-4/deploy.git
```

위 Clone 명령은 원격에 작업 브랜치를 Push한 뒤 실행합니다. 실제 저장소 이름이나 브랜치가 다르면 URL·브랜치를 바꿉니다. Backend/Frontend/FastAPI Jenkinsfile과 Backend Dockerfile 수정도 각 실제 저장소에 반영해야 합니다. 로컬 파일만 수정하면 Jenkins가 읽는 GitHub 코드에는 적용되지 않습니다.

PC에서 공통 EC2 키를 Jenkins 서버로 한 번 전달합니다. 아래는 **PC에서** 실행합니다.

```bash
scp -i /absolute/path/mirizoom.pem /absolute/path/mirizoom.pem ec2-user@JENKINS_PUBLIC_IP:/home/ec2-user/.ssh/mirizoom.pem
```

이후 명령은 **Jenkins 서버에서** 실행합니다.

```bash
chmod 400 /home/ec2-user/.ssh/mirizoom.pem
source /opt/mirizoom-bootstrap/bin/activate
cd /home/ec2-user/KB_PTJ/deploy
ansible-galaxy collection install -r ansible/requirements.yml
umask 077
mkdir -p .secrets ansible/inventory
touch .secrets/jenkins.env .secrets/app.env .secrets/frontend.env
touch ansible/inventory/bootstrap.yml
chmod 700 .secrets
chmod 600 .secrets/*.env ansible/inventory/bootstrap.yml
```

별도 example 파일은 관리하지 않습니다. 위 명령은 로컬 설정 파일만 만들며 기존 파일 내용을 지우지 않습니다. 아래 항목을 각 파일에 직접 입력합니다. 설정 파일과 SSH 키는 Git에 올리지 않습니다.

### `.secrets/jenkins.env`

```dotenv
JENKINS_ADMIN_ID=admin
JENKINS_ADMIN_PASSWORD=CHANGE_ME
GITHUB_USERNAME=CHANGE_ME
GITHUB_TOKEN=CHANGE_ME
DOCKERHUB_USERNAME=wosyh18
DOCKERHUB_TOKEN=CHANGE_ME
MIRIZOOM_KAKAO_JS_KEY=CHANGE_ME
BACKEND_REPOSITORY_URL=https://github.com/KB-IT-s-your-life-PJT-23-4/backend.git
FRONTEND_REPOSITORY_URL=https://github.com/KB-IT-s-your-life-PJT-23-4/frontend.git
FASTAPI_REPOSITORY_URL=https://github.com/KB-IT-s-your-life-PJT-23-4/FastApi.git
DEPLOY_REPOSITORY_URL=https://github.com/KB-IT-s-your-life-PJT-23-4/deploy.git
ENABLE_BATCH_SCHEDULE=false
```

관리자 ID와 비밀번호는 Jenkins 최초 실행 시 생성할 로그인 계정입니다. App/Web 주소, Docker GID, SSH 계정은 Bootstrap이 서버의 설정에 추가합니다.

### `.secrets/app.env`

```dotenv
BACKEND_TAG=latest
FASTAPI_TAG=latest
BATCH_TAG=latest
DB_HOST=CHANGE_ME
DB_PORT=3306
DB_NAME=mirizoom
DB_USERNAME=CHANGE_ME
DB_PASSWORD=CHANGE_ME
KAKAO_REST_API_KEY=CHANGE_ME
JWT_SECRET=CHANGE_ME
AI_CRYPTO_KEY_V1=CHANGE_ME
PII_HMAC_KEY_V1=CHANGE_ME
CLOVA_OCR_INVOKE_URL=
CLOVA_OCR_SECRET=
KRX_AUTH_KEY=CHANGE_ME
FSC_SECURITIES_API_KEY=CHANGE_ME
APP_ENV=production
OPENAI_API_KEY=CHANGE_ME
OPENAI_EMBEDDING_API_KEY=
CHROMA_PATH=/app/storage/chroma
MIRIZOOM_DB_HOST=CHANGE_ME
MIRIZOOM_DB_PORT=3306
MIRIZOOM_DB_NAME=mirizoom
MIRIZOOM_DB_USER=CHANGE_ME
MIRIZOOM_DB_PASSWORD=CHANGE_ME
MIRIZOOM_DB_CONNECT_TIMEOUT=5
BACKEND_JAVA_OPTS='-Xms128m -Xmx512m -XX:MaxMetaspaceSize=192m'
```

같은 RDS를 사용하면 `DB_*`와 `MIRIZOOM_DB_*`에 같은 주소·계정·스키마를 입력합니다. Host는 주소이고 User는 DB 로그인 계정입니다.

### `.secrets/frontend.env`

```dotenv
FRONTEND_TAG=latest
DOMAIN=_
BACKEND_PORT=8080
```

`BACKEND_HOST`는 Bootstrap이 App private IP로 추가합니다.

### `ansible/inventory/bootstrap.yml`

```yaml
all:
  vars:
    ansible_user: ec2-user
    ansible_ssh_private_key_file: /home/ec2-user/.ssh/mirizoom.pem
    ansible_python_interpreter: /usr/bin/python3
  children:
    jenkins:
      hosts:
        jenkins_server:
          ansible_connection: local
          ansible_host: 127.0.0.1
          private_ip: JENKINS_PRIVATE_IP
    app:
      hosts:
        app_server:
          ansible_host: APP_PRIVATE_IP
          private_ip: APP_PRIVATE_IP
    web:
      hosts:
        web_server:
          ansible_host: WEB_PRIVATE_IP
          private_ip: WEB_PRIVATE_IP
```

파일을 편집해 입력합니다.

- `bootstrap.yml`: 세 서버 private IP. Jenkins의 `ansible_host: 127.0.0.1`과 `ansible_connection: local`은 유지합니다. App/Web은 private IP로 접속합니다.
- `.secrets/jenkins.env`: 관리자 계정, GitHub·Docker Hub Token, Kakao Key, 실제 저장소 URL.
- `.secrets/app.env`: RDS와 API·암호화 키. Backend의 `DB_*`와 FastAPI의 `MIRIZOOM_DB_*`를 모두 입력합니다.
- `.secrets/frontend.env`: 초기 기본값 사용. Backend 주소는 Bootstrap이 채웁니다.

공백·`#`·`$`가 있는 값은 dotenv 문법에 따라 작은따옴표로 감쌉니다. `CHANGE_ME`를 모두 바꾸고 기존 서비스의 키 길이·인코딩 요구를 따릅니다. 실제 비밀값과 키는 Git에 커밋하지 않습니다.

Jenkins 서버에서 App/Web에 각각 한 번 접속해 private IP의 host key를 등록합니다. fingerprint는 AWS System Log와 비교합니다.

```bash
ssh -i /home/ec2-user/.ssh/mirizoom.pem ec2-user@APP_PRIVATE_IP
ssh -i /home/ec2-user/.ssh/mirizoom.pem ec2-user@WEB_PRIVATE_IP
```

확인 후 `exit`로 돌아옵니다. Host key 검증은 활성 상태로 유지합니다.

## 4. Jenkins 서버에서 최초 설정 실행

```bash
cd /home/ec2-user/KB_PTJ/deploy
python scripts/validate_config.py --secrets-dir .secrets --inventory ansible/inventory/bootstrap.yml
cd ansible
ansible -i inventory/bootstrap.yml all -m ping
ansible-playbook -i inventory/bootstrap.yml --syntax-check playbooks/bootstrap.yml
ansible-playbook -i inventory/bootstrap.yml playbooks/bootstrap.yml
```

Bootstrap은 자기 호스트와 App/Web에 Swap, Docker, Compose를 준비하고 Jenkins 이미지·JCasC를 적용합니다. Docker는 [AWS의 AL2023 설치 방식](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/create-container-image.html)을 사용합니다. Compose와 Buildx는 공식 GitHub 릴리스와 checksum으로 설치합니다. App/Web 서비스는 이 단계에서 시작하지 않습니다.

첫 이미지 빌드에는 시간이 걸립니다. 재적용은 Jenkins를 재시작하므로 진행 중인 Job이 없는 시점에 실행합니다. 기존 Jenkins volume, App/Web 환경 파일과 태그는 유지됩니다. 환경 파일의 비밀값을 변경하려면 서버 파일을 명시적으로 갱신해야 합니다. 초기 실행은 세 서버 전체를 대상으로 수행하며 `--limit`는 사용하지 않습니다.

## 5. PC에서 Jenkins 접속

PC의 새 터미널에서 아래 SSH 터널을 열어 둡니다. PC에 Ansible은 필요하지 않습니다.

```bash
ssh -i /absolute/path/mirizoom.pem -N -L 18080:127.0.0.1:8080 ec2-user@JENKINS_PUBLIC_IP
```

브라우저의 `http://localhost:18080`에서 입력한 관리자 계정으로 로그인합니다.

Job 6개: Backend CI, Frontend CI, FastAPI CI, Batch CI, `mirizoom-deploy`, `mirizoom-batch-scheduler` (기본 비활성).

Credentials 6개: `github-credentials`, `dockerhub-credentials`, `mirizoom-kakao-js-key`, `mirizoom-ec2-ssh`, `mirizoom-app-host`, `mirizoom-web-host`.

Job이 없으면 서버에서 Jenkins 로그의 JCasC/Job DSL 오류를 확인합니다. 로컬 지정 Job DSL 파일의 Script Security 승인이 필요하다고 표시되면 해당 스크립트인지 확인 후 In-process Script Approval에서 승인하고 재적용합니다.

## 6. 첫 서비스 배포

현재 Job DSL의 SCM 대상은 `develop`입니다. 작업 브랜치에서 먼저 실습하려면 `jenkins-infra/jobs/pipelines.groovy`의 `branch('*/develop')`를 `branch('*/feature_jenkins_ansible_cicd')`로 변경한 뒤 JCasC를 재적용합니다. 설정한 대상 브랜치에 각 저장소의 Jenkinsfile과 배포 파일을 Push한 상태에서 실행합니다.

1. `mirizoom-fastapi-ci`를 실행합니다. 성공 후 **Deploy Job도 완료됐는지** 확인합니다.
2. `mirizoom-backend-ci`를 실행하고 Deploy 완료를 확인합니다.
3. `mirizoom-frontend-ci`를 실행하고 Deploy 완료를 확인합니다.
4. 브라우저에서 `http://WEB_PUBLIC_IP`에 접속합니다. `http://WEB_PUBLIC_IP/api/ai/faq`도 확인합니다.
5. `mirizoom-batch-ci`를 실행합니다. 이 배포는 Batch 이미지를 pull하고 태그만 저장하며 실제 배치는 실행하지 않습니다.

CI는 Deploy를 비동기로 요청합니다. **CI 성공은 이미지 게시와 배포 요청 성공이며, 배포 성공은 `mirizoom-deploy`에서 확인**합니다. 실행 슬롯 1개에서 CI가 Deploy 완료를 기다리면 작업이 서로 기다릴 수 있기 때문에 분리했습니다. [Jenkins Build Step](https://www.jenkins.io/doc/pipeline/steps/pipeline-build-step/)

Deploy Job을 처음 생성한 후 Pipeline 파라미터가 아직 보이지 않으면 한 번 실행해 Jenkinsfile을 읽게 합니다. 이후 `Build with Parameters`에서 `SERVICE`, `IMAGE_TAG`를 확인할 수 있습니다. 이미 게시한 이미지로 수동 배포할 때는 **해당 CI의 이미지 태그**를 입력합니다.

FastAPI는 Compose healthcheck, Backend는 FAQ API 응답과 DB 접근, Frontend는 HTTP 200을 확인합니다. Backend FAQ가 실패하면 DB 스키마·테이블과 접속 값을 확인합니다. `docker ps`에 컨테이너가 보이는 것만으로 성공 처리하지 않습니다.

현재 코드에 자동 롤백은 없습니다. 새 버전 실패 시 Deploy가 실패하며 저장된 성공 태그는 유지합니다. 이전 태그로 Deploy를 다시 실행해 복구합니다. API 테스트 실패와 배포 실패를 숨기지 않습니다.

## 7. Batch 스케줄 켜기

Batch를 실제로 실행하면 DB 갱신이 발생할 수 있으므로 실습 DB와 필요한 API 설정을 먼저 준비합니다. 처음에는 스케줄을 켜지 않습니다.

1. Batch 이미지 배포 완료를 확인합니다.
2. Jenkins에서 Scheduler Job을 일시 활성화해 수동 실행하고 결과를 확인합니다. 수동 검증 중에는 정기 실행 시간과 겹치지 않도록 합니다.
3. 검증 후 `.secrets/jenkins.env`의 `ENABLE_BATCH_SCHEDULE=true`로 변경합니다.
4. Job이 실행 중이지 않은 시점에 전체 Bootstrap을 다시 적용합니다.
5. Scheduler Job이 활성화됐는지 확인합니다. Jenkinsfile을 한 번 실행하면 매주 일요일 한국 시간 03시대의 cron이 등록됩니다.

Batch 실행은 Ansible에서 `flock`으로 중복 실행을 막고, 이미 준비한 태그의 이미지를 사용합니다. `latest`를 새로 pull하지 않습니다.

## 파일 구성과 검증

- `jenkins-infra/user-data.sh`: Jenkins 호스트의 초기 Ansible 설치
- `jenkins-infra/Dockerfile`, `compose.yml`, `casc/`, `jobs/`: Jenkins 및 JCasC
- `deploy/ansible/inventory/`: localhost Jenkins와 private IP 대상 목록
- `deploy/ansible/playbooks/bootstrap.yml`: 최초 전체 설정
- `deploy/ansible/playbooks/deploy.yml`: 서비스 배포
- `deploy/ansible/playbooks/run-batch.yml`: Batch 실행
- `deploy/ansible/roles/swap/`, `docker/`, `server_config/`, `jenkins/`, `compose_deploy/`
- `deploy/scripts/validate_config.py`: 비밀값을 출력하지 않는 입력 검사

AWS 리소스 생성, DB 복원, Webhook, HTTPS 인증서, Blue-Green은 포함하지 않습니다. 초기에는 HTTP Nginx 템플릿을 사용하며 기존 HTTPS 템플릿은 별도로 보관합니다.

`VALIDATION.md`는 로컬 검사 범위와 AWS에서 추가로 확인할 항목을 기록합니다. 작은 서버에서의 실제 성능과 OOM 여부는 AWS 생성 후 확인해야 합니다.
