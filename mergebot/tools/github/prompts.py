GET_PULL_REQUEST_PROMPT = """
This tool will fetch the complete details of a pull request.
Example input: {\"pr_number\": \"10\"}
"""

POST_PULL_REQUEST_COMMENT_PROMPT = """
This tool is useful when you need to post a comment to a pull request in the Github repository.
    
For example, to post a comment "Looks good to me!" to pull request number 10:

Example input: {\"pr_number\": \"10\", \"comment\": \"Looks good to me!\"}

"""

APPROVE_MERGE_REQUEST_PROMPT = """
This tool is useful when you need to approve a pull request in a Github repository.
    
For example, to approve a pull request number 10:

Example input: {\"pr_number\": \"10\"}

"""
