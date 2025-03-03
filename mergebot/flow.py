import random
from crewai.flow.flow import Flow, listen, router, start, and_
from crewai import Crew
from pydantic import BaseModel
import re
from mergebot.crews.code_analysis.crew import CodeAnalysis

# Get the MR Processing Crew
code_analysis_crew = CodeAnalysis()
