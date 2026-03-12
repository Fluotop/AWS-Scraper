import boto3
import os
import base64

ec2 = boto3.client("ec2")
AMI_ID = os.environ["AMI_ID"]
INSTANCE_TYPE = os.environ["INSTANCE_TYPE"]

USER_DATA_SCRIPT = """#!/bin/bash
LOG_FILE="/home/ec2-user/scraper.log"
BUCKET="BDM060897"

echo "Starting scraper..." | tee -a $LOG_FILE

cd /home/ec2-user

git clone https://github.com/myorg/scraper-repo.git >> $LOG_FILE 2>&1
cd scraper-repo

python3 scraper.py >> $LOG_FILE 2>&1

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