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

/new task2 (loop silent failure guard)

Create a skill with the command /done_pr which 1. run /opsx:archive and 2. commit the spec updates. Finally, 3. `git checkout master && git pull`

/new task2 (trace schema writer)

/new_task2 (trace replay harness)

Add a new slash command locally called /review_task2 which 1. runs `codex exec "review the diff against master` 2. reads the comments from codex and summon a subagent with model = sonnet to fix the issue. 3. run /simplify 4. iterate the process until no code was changed since last commit. Otherwise, commit the changes.

/new_task2 (api server)

/new_task2 (eval runner)

Run the live script and let's discuss how we can improve the live tasks for unknown domains in a more general way.

Before ticket 19 and 20, can you add two tickets first? 
1. research on internet about web use benchmark, and integrate them into our developement.
2. Design a skill/update in the code that evaluate our agent in a quantitative way in terms of cost, correctness and latency.

/new_task2 (web-bench-integration)

Write a task2/smoke_test.sh to run the smoke test for task2 agent. Raise the api server in the script and kill it in the end.

Update /new_task2 skill to run task2/smoke_test.sh before making PR. Re-verify and /simplify if the smoke test does not pass.

Update /done_pr to insert benchmark results before the commit. Add a PR workflow that checks the results before merge.

/new_task2 (observe ax tree)

/new_task2 (plan-replan)

Create a script that - run after we finished the benchmark in /done_pr, - read all the results.json in task2/benchmark/*/ , - create different figures that will be displayed at the top of README.md , showcase the benchmark evolution over time.

/new_task2, and iterate different skills (ask claude to update the skill from what it has learned)

Can you check how we show the benchmark results in /done_pr , how we adjust the task2/README.md ? Propose a better way to visualize the benchmark evolution: 1. please add latest benchmark results as a table. 2. The latest benchmark has higher success rate, while the cost/latency got higher. But this is natural because we spend more steps on the successful task. Adjust the visualization to handle this.

I got a question for you. When writing skills, shall I divide different parts into different minor files, and read them when we are in the next step? I think this would help since we will only read the skill at the very beginning of the prompt process. Read different files make sure the implementations is more dynamic and that the implementation will be in more recent context.


Now, let's create a meta skill that call /full_task2 , then /review_task2 with subagent and finally /done_pr . How to make sure that these three skills will not pollute the context?

/full_task2 (with lots of iterations)

Let's check the benchmark results. Propose different ways to improve the benchmark in task2/plan.md

Update the skills from what you have learned. Please also update /done_pr to analyze why benchmark failed and add tickets to task2/plan.md

For each iteration in /new_task2 : pick the change most likely to flip the most red cases to green on the next benchmark run. Implement, run benchmark, report delta. Stop when pass-rate plateaus or demo time arrives.

Great. Let's archive the results in task2/RAEDME.md to a section called "basic_benchmark", and update the benchmark to the live one (web voyager)? Let's plan about this first.

---

For the rest, most of the developement is done automatically. Since claude allows adding prompt during run, I kept monitor the implementation and add follow up that I observed directly to task2/plan.md as a ticket. LLM is not reliable in the sense that it always try to solve the issues with special cases handler, while most of the time, a more general approach is preferred.

Update task2/plan.md format to have a INDEX.md + a folder of tickets. This helps for better token usages.
1. Parallelize independent tickets. Today /auto_task2 is strictly serial — one ticket, one PR, one merge, repeat. Many tickets touch disjoint files (e.g. #51 in score.py vs a UI/agent ticket vs a benchmark-script ticket). A "fan-out" mode could spawn N /full_task2 runs in parallel git worktrees, each on its own branch, with a serialization point only at merge time. The blocker is the WebVoyager benchmark in /done_pr 1a — it's live-only and can't run concurrently. Resolve by gating: parallel implementation phases, serial benchmark+merge phase.
2. Cheaper benchmark feedback loops. The WebVoyager run is the biggest single cost in /done_pr (multiple minutes + LLM cost + non-deterministic). For tickets that obviously can't move WebVoyager axes (process/standards tickets like #76, pure refactors, scoreboard math like #51), allow /done_pr to skip step 1a entirely and rely on the basic suite. The skill already has git diff --name-only origin/master...HEAD -- task2/ as a gate; tighten it to detect "agent-affecting" changes (anything under task2/agent/) vs scripts-only changes.
3. Skip review iterations 3+ when categorization is empty. /review_task2 currently runs the reviewer subagent every iteration. The skill's own notes say iterations 3+ "usually converge as no-op." Add an early-exit: if iteration N produced zero (a) findings AND no commits, don't dispatch the reviewer again — the diff didn't change.
4. Cache /opsx:ff artifact patterns. Many tickets generate near-identical proposal/tasks structures. A small templated proposal for "fix bug in script X" tickets would cut sonnet artifact-generation time.
5. Drop /simplify re-dispatches on unchanged diffs (already noted in review_task2 step 6 but worth enforcing harder).
