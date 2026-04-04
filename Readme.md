Windows에서 실행하는 방법

사전 준비
1. Docker Desktop 설치

docker.com/products/docker-desktop 에서 다운로드 후 설치
설치 완료 후 Docker Desktop 실행 → 트레이 아이콘이 초록색이 되면 준비 완료
2. 프로젝트 파일 복사
리눅스에서 Windows로 프로젝트 폴더 전체를 복사합니다.


auto_launch/
├── config/config.json    ← 로그인 정보, 스케줄, 키워드 설정
├── src/
├── Dockerfile
├── docker-compose.yml
└── requirements.txt

최초 1회 빌드
PowerShell 또는 명령 프롬프트(cmd)를 열고 프로젝트 폴더로 이동:
cd C:\경로\auto_launch

# 이미지 빌드 (3~5분 소요)
docker-compose build

실행
즉시 1회 실행 (테스트용)
docker-compose run --rm auto-launch python src/main.py --run-now

스케줄러 모드로 상시 실행 (PC 재부팅 시 자동 재시작)
docker-compose up -d

실행 중인 컨테이너 로그 확인
docker-compose logs -f

중지
docker-compose down

설정 변경 방법
config\config.json 파일을 메모장 등으로 수정하면 재빌드 없이 즉시 반영됩니다. (볼륨 마운트로 연결되어 있음)

변경 항목	위치
로그인 ID / 비밀번호
login.id, login.password

실행 요일/시간
schedule.time, schedule.day_of_week

대상 수업 키워드
keywords

브라우저 표시 여부
headless (Docker에서는 반드시 true)

주의: Docker 환경에서는 화면이 없으므로 headless를 반드시 true로 설정해야 합니다.

로그 / 스크린샷 위치
컨테이너 실행 후 Windows 파일 탐색기에서 바로 확인 가능합니다:

auto_launch\logs\          ← 날짜별 실행 로그
auto_launch\screenshots\   ← 오류 발생 시 캡처 이미지
