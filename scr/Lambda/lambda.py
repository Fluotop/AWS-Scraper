import boto3
import os
import base64

ec2 = boto3.client("ec2")
AMI_ID = os.environ["AMI_ID"]
INSTANCE_TYPE = os.environ["INSTANCE_TYPE"]

USER_DATA_SCRIPT = """#!/bin/bash
LOG_FILE="/home/ec2-user/scraper.log"
BUCKET="BDM060897"

echo "Starting download..." | tee -a $LOG_FILE

set -e

# install required packages
dnf update -y
dnf install -y git

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
cd /home/ec2-user/app

echo "Starting scraper..." | tee -a $LOG_FILE
python -m scrapers.category_manager >> $LOG_FILE 2>&1
python run_all_scrapers.py >> $LOG_FILE 2>&1

echo "Scraper finished" | tee -a $LOG_FILE

INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
REGION=$(curl -s http://169.254.169.254/latest/meta-data/placement/region)

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
                 "Project": "Scraper_Project"},
            ]
        }
    ]
    )