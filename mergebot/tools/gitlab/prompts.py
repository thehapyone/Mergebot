GET_MERGE_REQUEST_PROMPT = """
This tool will fetch the complete details of a specific merge request.
Example input: {\"merge_request_iid\": \"10\"}
"""

POST_MERGE_REQUEST_COMMENT_PROMPT = """
This tool is useful when you need to post a comment to a merge request in the GitLab repository.
    
For example, to post a comment "Looks good to me!" to merge request number 10:

Example input: {\"merge_request_iid\": \"10\", \"comment\": \"Looks good to me!\"}

"""

APPROVE_MERGE_REQUEST_PROMPT = """
This tool is useful when you need to approve a merge request in a GitLab repository.
    
For example, to approve a merge request number 10:

Example input: {\"merge_request_iid\": \"10\"}

"""

POST_MERGE_REQUEST_THREAD_COMMENT_PROMPT = """
This tool is useful when you need to post a reply to an existing comment thread in a merge request. **VERY IMPORTANT**: Your input to this tool MUST strictly follow these rules:
    
- First, you must specify the merge request number (IID) as an integer.
- Then, you must place two newlines.
- Then, you must specify the existing comment ID as an integer.
- Then, you must place two newlines.
- Then, you must specify your reply comment.
    
For example, to reply "I agree with your assessment." to comment ID 5 in merge request number 10, you would pass in the following string:

10

5

I agree with your assessment.
"""


FETCH_PIPELINE_DETAILS_PROMPT = """  
This tool will fetch detailed information of a specific pipeline, including job logs and summarized relevant information.  
Example input: {"pipeline_id": "12345"}  
"""
