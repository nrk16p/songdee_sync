pipeline {
    agent any

    triggers {
        cron('H/10 * * * *')
    }

    environment {
        // สร้าง credential แบบ "Username with password" ใน Jenkins ชื่อ id: vehtec-api
        VEHTEC_CRED = credentials('vehtec-api')
    }

    stages {
        stage('Setup') {
            steps {
                sh '''
                    # Install python3-venv if missing (Debian/Ubuntu Jenkins)
                    if ! python3 -m venv --help > /dev/null 2>&1; then
                        apt-get install -y python3-venv python3-full 2>/dev/null || true
                    fi

                    # Create venv and install deps
                    python3 -m venv venv
                    venv/bin/pip install --upgrade pip --quiet
                    venv/bin/pip install -r requirements.txt --quiet
                '''
            }
        }

        stage('Run GPS Sync') {
            steps {
                sh '''
                    export VEHTEC_USERNAME="$VEHTEC_CRED_USR"
                    export VEHTEC_PASSWORD="$VEHTEC_CRED_PSW"
                    venv/bin/python main.py
                '''
            }
        }
    }

    post {
        success {
            echo '✅ VehTec GPS sync completed successfully'
        }
        failure {
            echo '❌ VehTec GPS sync failed'
        }
    }
}
