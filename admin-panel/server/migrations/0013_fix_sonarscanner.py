"""
Fix SonarScanner command for local SonarQube:
- Remove sonar.organization (SonarCloud-only concept, breaks local SQ).
- Add sonar.host.url via SONAR_HOST_URL env var (default http://localhost:9000).
"""
from yoyo import step


def apply_step(conn):
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE verification_steps SET
            command = 'sonar-scanner -Dsonar.projectKey=$(basename $(pwd)) -Dsonar.host.url=${SONAR_HOST_URL:-http://localhost:9000} -Dsonar.token=${SONAR_TOKEN} -Dsonar.sources=.'
        WHERE name = 'SonarScanner'
    """)


step(apply_step)
