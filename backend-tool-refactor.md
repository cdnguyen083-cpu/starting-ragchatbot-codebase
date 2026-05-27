Refactor @backend/ai_generator.py to support sequential tool calling when Claude can make up to two calls in separate API rounds. 

Current behavior:
- Claude makes one tool call -> Tools are removed from API params -> Final response. 
- If Claude wants another tool call after seeing results, it can't (Get empty response)

Desired behavior:
- Each tool call should be a separate API request where Claude can reason about previous results.
- Support for complex queries requiring multiple searches for comparisons, multi-part questions, or when information from different courses/lessons is needed.  

Example flow:
1. User: "Search for a course that discusses the same topic as lesson 4 of course X."
2. Claude: Get course outline for Course X -> get title lesson 4. 
3. Claude: Use the title to search for a course that discusses the same topic -> return the course information. 
4. Claude: Provides complete answer 

Requirements:
- Maximum two sequential rounds per user query.
- Terminate when: (a) Two rounds completed, (b) Claude response has no tool_use blocks, or (c) tool call fail.
- Preserve conversation context between rounds.
- Handle tool execution errors gracefully.

Notes:
1. Update the system prompt in @backend/ai_generator.py
2. Update the test @backend/tests/test_ai_generator.py
3. Write tests that verify the external behavior (API calls made, tools executed, result returned) rather than internal state details.

Use two parallel sub-agents to brainstorm potential plans. Do not implement any code. 