Let's work on task 2 in @AI-Coding-Test-EN.md . Create a plan in task2/plan.md first.

Add a Trace schema in the plan so that we can replay decisions for debugging/developing.

---

/opsx:new implement the first task in @task2/plan.md

Let's create a skill that automate the developement process. I would need the followings: 1. a slash command called /new_task2 which read @task2/plan.md , derive the next ticket to do and 2. use /opsx:new to create a new openspec changes, 3. use /opsx:ff to create different artifacts for the ticket. 4. Commit the changes on a new developement branch with a `chore` message. 5. use /opsx:apply to start developing. Make sure to test, lint/format and finally commit during the developement. 6. Once finished, iterate through /opsx:verify and /simplify to check the integration, code reuse, code quality and code efficiency. Commit over the changes, too.

/new_task2 (l2)

Make the repository more standard: 1. add CI workflow for task2/ , which apply pytest and ruff for checks. PRs are not allowed to merge if the CI is not passed. 2. Add PULL_REQUEST_TEMPLATE.md 3. Add Dependabot 4. Add pytest-cov for coverage.

Update the /new_task2 skill to create a PR in the end.

/new_task2 (l3)

Update the /new_task2 skill to summon subagents for "Generate all artifacts", "Implement via /opsx:apply", "Verify".

Update PR template to draw diagram about what was introduced in the PR, including the states before and after the PR. Update the /new_task2 skill to read from template instead of owning a template itself.

/new_task2 (l4)

/new_task2 (locate cache)

Review /new_task2 and downgrade certain models' for the subagents that are not for planning purpose.

/new_task2 (supervisor)

/new_task2 (happy path)

/new_task2 (loop self correction)

Create a skill with the command /done_pr which 1. run /opsx:archive and 2. commit the spec updates. Finally, 3. `git checkout master && git pull`
