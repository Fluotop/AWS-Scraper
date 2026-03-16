import boto3

bucket = "bdm060897-prod"
prefix = "Products/"

s3 = boto3.client("s3")

paginator = s3.get_paginator("list_objects_v2")

for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
    if "Contents" in page:
        objects = [{"Key": obj["Key"]} for obj in page["Contents"]]

        s3.delete_objects(
            Bucket=bucket,
            Delete={"Objects": objects}
        )

print("Deleted all objects in prefix:", prefix)