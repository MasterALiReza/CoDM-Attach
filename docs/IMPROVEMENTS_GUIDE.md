# راهنمای بهبود نقاط ضعف پروژه

راهنمای جامع رفع نقاط ضعف و بهبود کیفیت

---

## 1. Testing Framework

### نصب
```bash
pip install pytest pytest-asyncio pytest-cov pytest-mock
```

### ساختار
```
tests/
├── __init__.py
├── conftest.py          # تنظیمات مشترک
├── unit/                # تست‌های واحد
│   ├── test_database.py
│   └── test_handlers.py
└── integration/         # تست‌های یکپارچه
    └── test_flows.py
```

### conftest.py
```python
import pytest
from unittest.mock import Mock

@pytest.fixture
def mock_db():
    db = Mock()
    db.get_weapons_in_category = Mock(return_value=['AK-47'])
    return db

@pytest.fixture
def mock_update():
    from telegram import Update, User
    update = Mock(spec=Update)
    update.effective_user = Mock(spec=User)
    update.effective_user.id = 12345
    return update
```

### نمونه تست
```python
# tests/unit/test_database.py
def test_add_weapon(mock_db):
    result = mock_db.add_weapon('assault_rifle', 'AK-47')
    assert result == True
```

### اجرا
```bash
pytest                           # همه تست‌ها
pytest --cov=. --cov-report=html # با coverage
```

---

## 2. CI/CD Pipeline

### GitHub Actions

**فایل `.github/workflows/test.yml`**:
```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:14
        env:
          POSTGRES_PASSWORD: postgres
        ports: ['5432:5432']
    
    steps:
    - uses: actions/checkout@v3
    - uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    - run: pip install -r requirements.txt pytest pytest-cov
    - run: pytest --cov=.
```

---

## 3. Monitoring

### Prometheus + Grafana

**فایل `core/monitoring/metrics.py`**:
```python
from prometheus_client import Counter, Histogram, start_http_server

message_counter = Counter('bot_messages_total', 'Messages')
response_time = Histogram('bot_response_seconds', 'Response time')

class MetricsCollector:
    def __init__(self, port=9090):
        start_http_server(port)
    
    @staticmethod
    def track_message():
        message_counter.inc()
```

### Docker Compose
```yaml
# docker-compose.monitoring.yml
services:
  prometheus:
    image: prom/prometheus
    ports: ['9090:9090']
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
  
  grafana:
    image: grafana/grafana
    ports: ['3000:3000']
```

### Sentry
```bash
pip install sentry-sdk
```

```python
# در main.py
import sentry_sdk
sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"))
```

---

## 4. Documentation

### MkDocs
```bash
pip install mkdocs mkdocs-material
mkdocs new docs
mkdocs serve  # Preview
mkdocs build  # Build
```

### Docstrings
```python
def add_weapon(self, category: str, weapon: str) -> bool:
    """
    اضافه کردن سلاح جدید
    
    Args:
        category: دسته سلاح
        weapon: نام سلاح
    
    Returns:
        bool: موفقیت/عدم موفقیت
    """
```

---

## 5. Docker

### Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

### docker-compose.yml
```yaml
version: '3.8'
services:
  bot:
    build: .
    env_file: .env
    depends_on: [postgres]
  
  postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: codm_bot
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

---

## 6. Code Quality

### Black (Formatter)
```bash
pip install black
black .  # Format همه فایل‌ها
```

### Flake8 (Linter)
```bash
pip install flake8
flake8 .
```

### Pre-commit
```bash
pip install pre-commit
```

**فایل `.pre-commit-config.yaml`**:
```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.12.0
    hooks:
      - id: black
  
  - repo: https://github.com/pycqa/flake8
    rev: 6.1.0
    hooks:
      - id: flake8
```

```bash
pre-commit install
```

---

## 7. Security

### Dependency Scanning
```bash
pip install safety
safety check
```

### Environment Variables
هرگز secrets رو commit نکن:
```bash
echo ".env" >> .gitignore
```

### Rate Limiting Enhancement
```python
# در core/security/rate_limiter.py
class AdvancedRateLimiter:
    def __init__(self):
        self.blocked_users = {}
    
    def is_blocked(self, user_id: int) -> bool:
        return user_id in self.blocked_users
```

---

## Checklist اجرایی

### هفته 1-2 (اولویت بالا)
- [ ] نصب pytest و نوشتن 20 تست
- [ ] تنظیم GitHub Actions
- [ ] نصب Sentry
- [ ] Docker Compose

### هفته 3-4 (اولویت متوسط)
- [ ] افزایش coverage به 60%
- [ ] Prometheus + Grafana
- [ ] Pre-commit hooks
- [ ] Documentation پایه

### هفته 5-6 (اولویت پایین)
- [ ] Coverage 80%+
- [ ] Documentation کامل
- [ ] Security scanning
- [ ] Custom Grafana dashboards

---

## معیارهای موفقیت

- Test Coverage: 80%+
- CI/CD: همه تست‌ها pass
- Response Time: <200ms (P95)
- Error Rate: <1%
- Uptime: 99.9%

---

## منابع مفید

- [pytest Documentation](https://docs.pytest.org)
- [GitHub Actions](https://docs.github.com/actions)
- [Prometheus](https://prometheus.io/docs)
- [Docker](https://docs.docker.com)
