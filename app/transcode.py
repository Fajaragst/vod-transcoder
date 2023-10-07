import os
import boto3
import logging
import json
import subprocess
import logging
import datetime

from urllib.parse import unquote_plus
from time import sleep

from botocore.exceptions import ClientError


sqs = boto3.client('sqs', region_name='ap-southeast-1')
s3 = boto3.client('s3', region_name='ap-southeast-1')

BUCKET_VIDEO_NAME = os.getenv('BUCKET_VIDEO_NAME', 'transcoded-video')

S3_PRESIGNED_URL_EXPIRATION = int(os.getenv('S3_PRESIGNED_URL_EXPIRATION', 1800))

SQS_QUEUE_URL = os.getenv('SQS_QUEUE_URL')
SQS_VISIBILITY_TIMEOUT = int(os.getenv('SQS_VISIBILITY_TIMEOUT', 3600))
SQS_WAIT_TIME_SECONDS = int(os.getenv('SQS_WAIT_TIME_SECONDS', 20))



def create_presigned_url(bucket_name, key, expiration=S3_PRESIGNED_URL_EXPIRATION):
    """Generate a presigned URL to share an S3 object

    :param bucket_name: string
    :param object_name: string
    :param expiration: Time in seconds for the presigned URL to remain valid
    :return: Presigned URL as string. If error, returns None.
    """
    try:
        response = s3.generate_presigned_url('get_object',
                                                    Params={'Bucket': bucket_name,
                                                            'Key': key},
                                                    ExpiresIn=expiration)
    except ClientError as e:
        logging.error(e)
        return None

    return response

def transcode(url, file_name):
    bashCommand =  ["bash", "app/transcode.sh", "-u", url, "-n", file_name] 
    # with open('log/' + file_name + '.log', 'w+') as f:
    #     process = subprocess.Popen(bashCommand, stdout=f)
    #     output, error = process.communicate()
    process = subprocess.Popen(bashCommand, stdout=subprocess.PIPE)
    output, error = process.communicate()
    return process

def delete_dir(dir_name):
    bashCommand =  ["rm", "-r", dir_name] 
    process = subprocess.Popen(bashCommand, stdout=subprocess.PIPE)
    output, error = process.communicate()
    return process

def upload(local_directory, bucket, destination):

    # enumerate local files recursively
    for root, dirs, files in os.walk(local_directory):
        
        for filename in files:

            # construct the full local path
            local_path = os.path.join(root, filename)

            # construct the full Dropbox path
            relative_path = os.path.relpath(local_path, local_directory)
            s3_path = os.path.join(destination, relative_path)

            print ('Searching "%s" in "%s"' % (s3_path, bucket))
            try:
                s3.head_object(Bucket=bucket, Key=s3_path)
                print ("Path found on S3! Skipping %s..." % s3_path)

            except:
                print ("Uploading %s..." % s3_path)
                s3.upload_file(local_path, bucket, s3_path)


while(True):
    response = sqs.receive_message(
        QueueUrl=SQS_QUEUE_URL,
        AttributeNames=['SentTimestamp'],
        MaxNumberOfMessages=1,
        MessageAttributeNames=['All'],
        VisibilityTimeout=SQS_VISIBILITY_TIMEOUT,
        WaitTimeSeconds=SQS_WAIT_TIME_SECONDS
    )

    for message in response.get("Messages", []):

        try:

            message_body = json.loads(message["Body"])
            bucket_name = message_body["Records"][0]["s3"]["bucket"]["name"]
            key = message_body["Records"][0]["s3"]["object"]["key"]

            print(f"Receipt Handle: {message['ReceiptHandle']}")
            key_unquote = unquote_plus(key)
            key_unquote_without_extension = os.path.splitext(key_unquote)[0]

            url = create_presigned_url(bucket_name, key_unquote)

            transcode_res = transcode(url, key_unquote_without_extension)
            if transcode_res.returncode != 0:
                raise Exception("TRANSCODE FAIL,",key_unquote, ",retry in 1 hour")

            upload(os.path.splitext(key_unquote)[0], BUCKET_VIDEO_NAME, key_unquote_without_extension)
            delete_dir(key_unquote_without_extension)

            # Delete received message from queue
            receipt_handle = message['ReceiptHandle']
            sqs.delete_message(
                QueueUrl=SQS_QUEUE_URL,
                ReceiptHandle=receipt_handle
            )
            print('Received and deleted message: %s' % message)
            
        except Exception as e:
            pass
    
    sleep(60)