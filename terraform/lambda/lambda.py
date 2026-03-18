import boto3
import os
import base64

ec2 = boto3.client("ec2")
AMI_ID = os.environ["AMI_ID"]
INSTANCE_TYPE = os.environ["INSTANCE_TYPE"]

USER_DATA_SCRIPT = """#!/bin/bash
set -e
set -x
exec > >(tee /home/ec2-user/full-debug.log) 2>&1

LOG_FILE="/home/ec2-user/scraper.log"
BUCKET="bdm060897-prod"

echo "Starting download..." | tee -a $LOG_FILE

set -e
 
# install required packages
dnf update -y
dnf install -y git python3.11 python3-pip
python3.11 -m venv venv
source venv/bin/activate

# create ssh directory
mkdir -p /home/ec2-user/.ssh
chmod 700 /home/ec2-user/.ssh

# retrieve private key from Parameter Store
aws ssm get-parameter \
  --name "github_deploy_key" \
  --with-decryption \
  --query "Parameter.Value" \
  --output text \
  > /home/ec2-user/.ssh/id_ed25519

# fix permissions
chmod 600 /home/ec2-user/.ssh/id_ed25519
chown ec2-user:ec2-user /home/ec2-user/.ssh/id_ed25519

# add github to known hosts
ssh-keyscan github.com >> /home/ec2-user/.ssh/known_hosts
chown ec2-user:ec2-user /home/ec2-user/.ssh/known_hosts

# clone repository
sudo -u ec2-user git clone git@github.com:Fluotop/AWS-scraper.git /home/ec2-user/app
cd /home/ec2-user/app/src/
python3 -m pip install -r requirements.txt


echo "Starting category scraper..." | tee -a $LOG_FILE

set +e  # allow errors
cd /home/ec2-user/app/src

echo "Starting category scraper..." | tee -a $LOG_FILE
python3 -m scraper.scrapers.category_manager >> $LOG_FILE 2>&1

echo "Starting scraper..." | tee -a $LOG_FILE
python3 -m scraper.run_all_scrapers >> $LOG_FILE 2>&1
SCRAPER_EXIT=$?

set -e  # turn strict mode back on

echo "Scraper finished" | tee -a $LOG_FILE

TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

INSTANCE_ID=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" \
  -s http://169.254.169.254/latest/meta-data/instance-id)

AZ=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" \
  -s http://169.254.169.254/latest/meta-data/placement/availability-zone)

REGION=${AZ::-1}

echo "Uploading logs to S3..." | tee -a $LOG_FILE

aws s3 cp $LOG_FILE s3://$BUCKET/logs/scraper.log --region $REGION

aws ec2 terminate-instances --instance-ids $INSTANCE_ID --region $REGION
"""

def lambda_handler(event, context):
    ec2.run_instances(
        ImageId=AMI_ID,
        InstanceType=INSTANCE_TYPE,
        MinCount=1,
        MaxCount=1,
        IamInstanceProfile={
        'Name': 'scraper_ec2_profile'
        },
        
        UserData=base64.b64encode(USER_DATA_SCRIPT.encode()).decode(),
        
        TagSpecifications=[
        {
            "ResourceType": "instance",
            "Tags": [
                {"Key": "Name", "Value": "scraper-instance",
                 "Key": "project", "Value": "scraper-project"},
            ]
        }
    ]
    )