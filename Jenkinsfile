pipeline {
    agent any

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timeout(time: 15, unit: 'MINUTES')
        timestamps()
    }

    parameters {
        choice(
            name: 'SERVICE',
            choices: ['frontend', 'backend', 'fastapi', 'batch'],
            description: '배포할 서비스'
        )
        string(
            name: 'IMAGE_TAG',
            defaultValue: 'latest',
            description: 'Docker Hub에 Push된 이미지 태그'
        )
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Validate') {
            steps {
                sh '''
                    set -eu

                    case "$SERVICE" in
                        frontend|backend|fastapi|batch) ;;
                        *) echo "지원하지 않는 서비스입니다: $SERVICE" >&2; exit 1 ;;
                    esac

                    if ! printf '%s' "$IMAGE_TAG" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'; then
                        echo "잘못된 Docker 이미지 태그입니다: $IMAGE_TAG" >&2
                        exit 1
                    fi

                    ansible-playbook --version
                    test -f ansible/ansible.cfg
                    test -f ansible/playbooks/deploy.yml
                    test -f docker-compose.frontend.yml
                    test -f docker-compose.backend.yml
                    test -f nginx/default.conf.template
                '''
            }
        }

        stage('Deploy') {
            steps {
                withCredentials([
                    sshUserPrivateKey(
                        credentialsId: 'mirizoom-ec2-ssh',
                        keyFileVariable: 'SSH_KEY',
                        usernameVariable: 'SSH_USER'
                    ),
                    string(credentialsId: 'mirizoom-web-host', variable: 'WEB_HOST'),
                    string(credentialsId: 'mirizoom-app-host', variable: 'APP_HOST'),
                    usernamePassword(
                        credentialsId: 'dockerhub-credentials',
                        usernameVariable: 'DOCKERHUB_USERNAME',
                        passwordVariable: 'DOCKERHUB_TOKEN'
                    )
                ]) {
                    dir('ansible') {
                        sh '''
                            set -eu
                            set +x
                            export ANSIBLE_CONFIG="$PWD/ansible.cfg"
                            ansible-playbook --syntax-check playbooks/deploy.yml
                            ansible-playbook playbooks/deploy.yml
                        '''
                    }
                }
            }
        }
    }

    post {
        success {
            echo "${params.SERVICE}:${params.IMAGE_TAG} 배포가 완료되었습니다."
        }
        failure {
            echo "${params.SERVICE}:${params.IMAGE_TAG} 배포에 실패했습니다."
        }
        cleanup {
            deleteDir()
        }
    }
}
