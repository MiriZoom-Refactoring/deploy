# 로컬 검증 결과

검증일: 2026-10-12 (한국 시간)

대상 구성: Amazon Linux 2023 x86_64 3대. 초기 Ansible은 Jenkins EC2 호스트에서 실행하고, 이후 배포는 Jenkins 컨테이너의 Ansible에서 실행합니다.

- Bootstrap·Deploy·Batch Playbook 문법 검사를 통과했습니다.
- YAML 파싱, Role 파일 경로 및 Ansible 모듈 14개의 실제 지원 파라미터 검사를 통과했습니다.
- Amazon Linux 계정 ec2-user와 Jenkins 로컬 연결 Inventory 입력 검사를 통과했습니다.
- User data 스크립트의 Bash 문법을 확인했습니다.
- 실제 Amazon Linux 2023 임시 컨테이너에서 Git, Python 3.11, pip, Docker 패키지가 설치되는 것을 확인했습니다. 확인된 Python은 3.11.16, Docker는 25.0.14입니다.
- Jenkins·App Compose 설정 검사를 통과했습니다.
- Docker Buildx를 포함하는 Jenkins 이미지를 빌드했습니다.
- heap 최대 512 MiB를 적용한 임시 Jenkins에서 JCasC Job 6개, Credentials 6개, Scheduler 기본 비활성을 확인했습니다.
- Jenkins Declarative Pipeline 검사로 Backend·Batch·Frontend·FastAPI·Deploy·Scheduler Jenkinsfile을 검증했습니다.

실제 AWS 서버가 없어 systemd 서비스 시작, Swap 적용, SSH, RDS/API 연결, 소형 서버에서의 전체 빌드와 서비스 실행은 아직 확인하지 않았습니다. Docker 검증은 Mac ARM의 임시 환경에서 수행했으며 사용자 실행 절차는 Jenkins EC2 기준입니다.

Backend Dockerfile과 CI의 Gradle 설정은 worker 1개와 heap 최대 512 MiB로 조정했습니다. 이 메모리 설정으로 실제 애플리케이션 전체 빌드·테스트가 통과하는지는 첫 AWS CI 실행 때 확인해야 합니다. Swap은 메모리 부족을 완충하지만 성능이나 OOM 방지를 보장하지 않습니다.
