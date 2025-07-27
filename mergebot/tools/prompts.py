GET_PULL_REQUEST_PROMPT = """
This tool will fetch the complete details of a pull or merge request.
Example input: {\"pr_number\": \"10\"}
"""

POST_PULL_REQUEST_COMMENT_PROMPT = """
This tool is useful when you need to post a comment to a pull or merge request in the repository.
    
For example, to post a comment "Looks good to me!" to pull or merge request number 10:

Example input: {\"pr_number\": \"10\", \"comment\": \"Looks good to me!\"}

"""

APPROVE_MERGE_REQUEST_PROMPT = """
This tool is useful when you need to approve a pull or merge request in a repository.
    
For example, to approve a pull or merge request number 10:

Example input: {\"pr_number\": \"10\"}

"""


FETCH_PIPELINE_DETAILS_PROMPT = """
This tool will fetch detailed information of a specific pipeline, including job logs and summarized relevant information.  
Example input: {"pipeline_id": "12345"}  
"""


POST_PULL_REQUEST_THREAD_COMMENT_PROMPT = """
This tool is useful when you need to post a reply to an existing comment thread in a merge request. 

For example, to reply "I agree with your assessment." to comment ID 5 in merge request number 10, you would pass in the following string:

Example input: {\"pr_number\": \"10\", \"comment\": \"I agree with your assessment.\", \"thread_comment_id\": \"5\"}

"""
