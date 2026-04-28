

## Responsible AI

### Limitations and biases

The knowledge base is the most significant source of bias. The 7 documents were written using ChatGPT and reflect general Western veterinary guidelines. They don't account for things like breed differences or differences in available medications. If a user's pet has a condition not covered in the knowledge base, the retriever returns nothing relevant and Claude falls back on its training data, which has no transparency.

### Misuse potential and mitigations

The most likely misuse is an owner treating the AI’s explanation as a replacement for actual veterinary advice. The app can explain why something like medication timing matters, but it doesn’t know a pet’s exact diagnosis, current dosage, or any recent changes from the vet. That creates a real risk where someone could follow the schedule and overlook an updated instruction.
To reduce that risk, the app should include a clear, persistent disclaimer that its explanations are general guidance, not medical advice. It would also help to flag when a pet’s condition doesn’t have a matching document in the knowledge base, so the user knows the explanation may be incomplete or missing important context.

### Collaboration with AI during this project

AI assistance was used throughout the build, most heavily during the agent architecture design and the knowledge base content. 
When introducing RAG, AI was able to generate documentation such as the arthiritis.md and obesity.md, and connect that with the LLM. It was so nice to see that there was actual proof that the AI features in the PawPal were using the documents when possible.
The boilerplate code felt a little off at times. For example, I was not a fan of how it generated default values for pet names, ages, and task times. I removed these default generated values on my own so that it becomes more obvious that users have to plant them themselves.


## Reflection

Building PawPal+ with an AI layer taught me that the most valuable thing an LLM can do is explain the decision making really well. The rule based planner already makes the scheduling decisions, and Claude's job is to translate those decisions into something the owner can understand and act on. That's a much more reliable and testable use of an LLM than asking it to do the planning itself.

RAG reinforced how much grounding matters. Without the knowledge base, Claude's explanations were generic ("this task has high priority"). With the document based specifics, they referenced specific care guidelines tied to the pet's actual health conditions. The difference in output quality was pretty significant.