## documentation and markdown

if you HAVE to create a markdown file do it in docs/history directory 
## Important Rules

- ✅ Use bd for ALL task tracking
- ✅ Always use `--json` flag for programmatic use
- ✅ Link discovered work with `discovered-from` dependencies
- ✅ Check `bd ready` before asking "what should I work on?"
- ✅ Store AI planning docs in `history/` directory
- ❌ Do NOT create markdown TODO lists
- ❌ Do NOT use external issue trackers
- ❌ Do NOT duplicate tracking systems
- ❌ Do NOT clutter repo root with planning documents

## Issue Tracking

Use the `bd` command for all issue tracking instead of markdown TODOs:

- Create issues: `bd create "Task description" -p 1 --json`
- Find work: `bd ready --json`
- Update status: `bd update <id> --status in_progress --json`
- View details: `bd show <id> --json`

Use `--json` flags for programmatic parsing.

### Referencing Claude Agents in Issues

When creating bd issues, **always include a recommendation for which Claude Code agent should handle the work** in the issue description. This enables efficient task delegation and ensures the right specialized agent is used.

**Available Claude Agents:**
- **complexity-reducer**: Refactor high-complexity functions (CC > 9)
- **boundary-architect**: Setup and maintain boundary library for architecture enforcement
- **docs-writer**: Technical documentation, coding standards, guides
- **ci-architect**: CI/CD pipeline setup and optimization
- **matrix-helm-packager**: Helm chart updates and packaging
- **k8s-log-analyzer**: Kubernetes log analysis and pod troubleshooting
- **git-change-verifier**: Run quality checks after code changes
- **capi-cluster-manager**: CAPI infrastructure and cluster management
- **local-cluster**: Local Kubernetes environment management

**Issue Creation Pattern:**

```bash
bd create "Fix high complexity in LLM.do_execute (CC: 92)" \
  -p 1 \
  --description "Reduce cyclomatic complexity from 92 to <10 using function extraction.

**Recommended Agent:** complexity-reducer

**Current State:**
- File: apps/matrix_handoff/lib/matrix_handoff/task_executors/llm.ex
- Function: do_execute/2
- Complexity: 92

**Target:**
- Complexity: < 10
- Extract helper functions
- Maintain test coverage

**Verification:**
- Run mix credo to verify CC reduction
- Run mix test to ensure no regressions
- Verify all tests pass" \
  --json
```

**Agent Selection Guide:**

| Task Type | Recommended Agent |
|-----------|-------------------|
| Reduce function complexity | complexity-reducer |
| Add/refactor backend feature | python-backend-architect |
| Setup architecture boundaries | boundary-architect |
| Write/update documentation | docs-writer |
| CI/CD pipeline changes | ci-architect |
| Helm chart updates | matrix-helm-packager |
| Debug Kubernetes issues | k8s-log-analyzer |
| Verify code quality | git-change-verifier |
| Local K8s environment | local-cluster |
| Test feature | local-cluster |

### Issue Requirements

when creating issues make sure you use your best judgement on what needs to be there but include at least these additional instructions.

0. mark that you are taking it in the description. if it hasn't been picked up by another agent  in the past 10 minutes go ahead and take it.
1. verify your problem with tools at your disposal.
2. if ui, use client side ui tools to test the case.
3. if ui, once fixed and verified with the client tools, write a live view test case around it

## Session Start Checklist

**At the start of every session, ALWAYS:**

- [ ] Run `bd ready --json` to see available work
- [ ] Run `bd list --status in_progress --json` for active work
- [ ] If in_progress exists: `bd show <issue-id>` to read notes
- [ ] Report context to user: "X items ready: [summary]"
- [ ] If using global ~/.beads, mention this in report
- [ ] If nothing ready: `bd blocked --json` to check blockers

**For all issues worked on:**

0. mark that you are taking it in the description. if it hasn't been picked up by another agent in the past 10 minutes go ahead and take it.
1. verify your problem with tools at your disposal.
2. if ui, use client side ui tools to test the case. browser_eval specifically
3. if ui, once fixed and verified with the client tools, write a live view test case around it
4. make sure there is code coverage of the new code at least with 80% of new code
5. make sure we break down the test cases to keep them dry for the separation layers
6. test cases must trace back to the features, as well as the issue summary at the top of the test case

## Project guidelines

-- Use the project's standard linters and formatters and fix issues before committing new code

### JS and CSS guidelines

- **Use Tailwind CSS classes and custom CSS rules** to create polished, responsive, and visually stunning interfaces.
- Tailwindcss v4 **no longer needs a tailwind.config.js** and uses a new import syntax in `app.css`:

      @import "tailwindcss" source(none);
      @source "../css";
      @source "../js";
      @source "../../lib/my_app_web";

- **Always use and maintain this import syntax** in the app.css file for projects generated with `phx.new`
- **Never** use `@apply` when writing raw css
- Out of the box **only the app.js and app.css bundles are supported**
  - You cannot reference an external vendor'd script `src` or link `href` in the layouts
  - You must import the vendor deps into app.js and app.css to use them
  - **Never write inline <script>custom js</script> tags within templates**

### UI/UX & design guidelines

- **Produce world-class UI designs** with a focus on usability, aesthetics, and modern design principles
- Implement **subtle micro-interactions** (e.g., button hover effects, and smooth transitions)
- Ensure **clean typography, spacing, and layout balance** for a refined, premium look
- Focus on **delightful details** like hover effects, loading states, and smooth page transitions
### Additional Notes

#### heroicons

Always use heroicons when possible instead of generating your own SVGs.  There is a Phoenix Component named MatrixAdminConsole.CoreComponents.icon that you can use like this:

    <.icon name="hero-check-circle" class="h-8 w-8" />

It will need to be imported by one of the LiveView macros (try not to add a new import if possible) or referenced with the fully qualified name of MatrixAdminConsole.CoreComponents.icon.

#### Tailwind CSS Classes

Prefer Tailwind CSS classes on the elements themselves over custom CSS in app.css, but **please** try to avoid having a ridiculously long list of CSS classes on the elements themselves so the code isn't hard to read.
- HEEx class attrs support lists, but you must **always** use list `[...]` syntax. You can use the class list syntax to conditionally add classes, **always do this for multiple class values**:

      <a class={[
        "px-2 text-white",
        @some_flag && "py-5",
        if(@other_condition, do: "border-red-500", else: "border-blue-100"),
        ...
      ]}>Text</a>

  and **always** wrap `if`'s inside `{...}` expressions with parens, like done above (`if(@other_condition, do: "...", else: "...")`)

  and **never** do this, since it's invalid (note the missing `[` and `]`):

      <a class={
        "px-2 text-white",
        @some_flag && "py-5"
      }> ...
      => Raises compile syntax error on invalid HEEx attr syntax

- **Never** use `<% Enum.each %>` or non-for comprehensions for generating template content, instead **always** use `<%= for item <- @collection do %>`
- HEEx HTML comments use `<%!-- comment --%>`. **Always** use the HEEx HTML comment syntax for template comments (`<%!-- comment --%>`)
- HEEx allows interpolation via `{...}` and `<%= ... %>`, but the `<%= %>` **only** works within tag bodies. **Always** use the `{...}` syntax for interpolation within tag attributes, and for interpolation of values within tag bodies. **Always** interpolate block constructs (if, cond, case, for) within tag bodies using `<%= ... %>`.

  **Always** do this:

      <div id={@id}>
        {@my_assign}
        <%= if @some_block_condition do %>
          {@another_assign}
        <% end %>
      </div>

  and **Never** do this – the program will terminate with a syntax error:

      <%!-- THIS IS INVALID NEVER EVER DO THIS --%>
      <div id="<%= @invalid_interpolation %>">
        {if @invalid_block_construct do}
        {end}
      </div>

## Phoenix LiveView guidelines

- **Never** use the deprecated `live_redirect` and `live_patch` functions, instead **always** use the `<.link navigate={href}>` and  `<.link patch={href}>` in templates, and `push_navigate` and `push_patch` functions LiveViews
- **Avoid LiveComponent's** unless you have a strong, specific need for them
- Prefer the stateless component pattern
- LiveViews should be named like `AppWeb.WeatherLive`, with a `Live` suffix. When you go to add LiveView routes to the router, the default `:browser` scope is **already aliased** with the `AppWeb` module, so you can just do `live "/weather", WeatherLive`
- Remember anytime you use `phx-hook="MyHook"` and that js hook manages its own DOM, you **must** also set the `phx-update="ignore"` attribute
- **Never** write embedded `<script>` tags in HEEx. Instead always write your scripts and hooks in the `assets/js` directory and integrate them with the `assets/js/app.js` file

### JavaScript Hooks and Event Communication

- **Colocated Hooks**: Use `:type={Phoenix.LiveView.ColocatedHook}` with dot-prefixed hook names (`.PhoneNumber`) for inline hook definitions
- **External Hooks**: Define hooks in `assets/js/` and register them with the LiveSocket constructor
- **Server-to-Client Events**: Use `push_event/3` from the server to send events to client-side hooks, which respond with `this.handleEvent()`
- **Client-to-Server Events**: Client hooks use `this.pushEvent()` to send events to the server, handled by `handle_event/3` callbacks

### LiveView streams

- **Always** use LiveView streams for collections for assigning regular lists to avoid memory ballooning and runtime termination with the following operations:
  - basic append of N items - `stream(socket, :messages, [new_msg])`
  - resetting stream with new items - `stream(socket, :messages, [new_msg], reset: true)` (e.g. for filtering items)
  - prepend to stream - `stream(socket, :messages, [new_msg], at: -1)`
  - deleting items - `stream_delete(socket, :messages, msg)`

- When using the `stream/3` interfaces in the LiveView, the LiveView template must 1) always set `phx-update="stream"` on the parent element, with a DOM id on the parent element like `id="messages"` and 2) consume the `@streams.stream_name` collection and use the id as the DOM id for each child. For a call like `stream(socket, :messages, [new_msg])` in the LiveView, the template would be:

      <div id="messages" phx-update="stream">
        <div :for={{id, msg} <- @streams.messages} id={id}>
          {msg.text}
        </div>
      </div>

- LiveView streams are *not* enumerable, so you cannot use `Enum.filter/2` or `Enum.reject/2` on them. Instead, if you want to filter, prune, or refresh a list of items on the UI, you **must refetch the data and re-stream the entire stream collection, passing reset: true**:

      def handle_event("filter", %{"filter" => filter}, socket) do
        # re-fetch the messages based on the filter
        messages = list_messages(filter)

        {:noreply,
        socket
        |> assign(:messages_empty?, messages == [])
        # reset the stream with the new messages
        |> stream(:messages, messages, reset: true)}
      end

- LiveView streams *do not support counting or empty states*. If you need to display a count, you must track it using a separate assign. For empty states, you can use Tailwind classes:

      <div id="tasks" phx-update="stream">
        <div class="hidden only:block">No tasks yet</div>
        <div :for={{id, task} <- @stream.tasks} id={id}>
          {task.name}
        </div>
      </div>

  The above only works if the empty state is the only HTML block alongside the stream for-comprehension.

- **Never** use the deprecated `phx-update="append"` or `phx-update="prepend"` for collections

### LiveView tests

- `Phoenix.LiveViewTest` module and `LazyHTML` (included) for making your assertions
- Form tests are driven by `Phoenix.LiveViewTest`'s `render_submit/2` and `render_change/2` functions
- Come up with a step-by-step test plan that splits major test cases into small, isolated files. You may start with simpler tests that verify content exists, gradually add interaction tests
- **Always reference the key element IDs you added in the LiveView templates in your tests** for `Phoenix.LiveViewTest` functions like `element/2`, `has_element/2`, selectors, etc
- **Never** tests again raw HTML, **always** use `element/2`, `has_element/2`, and similar: `assert has_element?(view, "#my-form")`
- Instead of relying on testing text content, which can change, favor testing for the presence of key elements
- Focus on testing outcomes rather than implementation details
- Be aware that `Phoenix.Component` functions like `<.form>` might produce different HTML than expected. Test against the output HTML structure, not your mental model of what you expect it to be
- When facing test failures with element selectors, add debug statements to print the actual HTML, but use `LazyHTML` selectors to limit the output, ie:

      html = render(view)
      document = LazyHTML.from_fragment(html)
      matches = LazyHTML.filter(document, "your-complex-selector")
      IO.inspect(matches, label: "Matches")

### Form handling

#### Creating a form from params

If you want to create a form based on `handle_event` params:

    def handle_event("submitted", params, socket) do
      {:noreply, assign(socket, form: to_form(params))}
    end

When you pass a map to `to_form/1`, it assumes said map contains the form params, which are expected to have string keys.

You can also specify a name to nest the params:

    def handle_event("submitted", %{"user" => user_params}, socket) do
      {:noreply, assign(socket, form: to_form(user_params, as: :user))}
    end

#### Creating a form from changesets

When using changesets, the underlying data, form params, and errors are retrieved from it. The `:as` option is automatically computed too. E.g. if you have a user schema:

    defmodule MyApp.Users.User do
      use Ecto.Schema
      ...
    end

And then you create a changeset that you pass to `to_form`:

    %MyApp.Users.User{}
    |> Ecto.Changeset.change()
    |> to_form()

Once the form is submitted, the params will be available under `%{"user" => user_params}`.

In the template, the form form assign can be passed to the `<.form>` function component:

    <.form for={@form} id="todo-form" phx-change="validate" phx-submit="save">
      <.input field={@form[:field]} type="text" />
    </.form>

Always give the form an explicit, unique DOM ID, like `id="todo-form"`.

#### Avoiding form errors

**Always** use a form assigned via `to_form/2` in the LiveView, and the `<.input>` component in the template. In the template **always access forms this**:

    <%!-- ALWAYS do this (valid) --%>
    <.form for={@form} id="my-form">
      <.input field={@form[:field]} type="text" />
    </.form>

And **never** do this:

    <%!-- NEVER do this (invalid) --%>
    <.form for={@changeset} id="my-form">
      <.input field={@changeset[:field]} type="text" />
    </.form>

- You are FORBIDDEN from accessing the changeset in the template as it will cause errors
- **Never** use `<.form let={f} ...>` in the template, instead **always use `<.form for={@form} ...>`**, then drive all form references from the form assign as in `@form[:field]`. The UI should **always** be driven by a `to_form/2` assigned in the LiveView module that is derived from a changeset

### Additional Notes

#### heroicons

Always use heroicons when possible instead of generating your own SVGs.  There is a Phoenix Component named MatrixAdminConsole.CoreComponents.icon that you can use like this:

    <.icon name="hero-check-circle" class="h-8 w-8" />

It will need to be imported by one of the LiveView macros (try not to add a new import if possible) or referenced with the fully qualified name of MatrixAdminConsole.CoreComponents.icon.

#### Tailwind CSS Classes

Prefer Tailwind CSS classes on the elements themselves over custom CSS in app.css, but **please** try to avoid having a ridiculously long list of CSS classes on the elements themselves so the code isn't hard to read.

## Implementation and Validation Workflow

**CRITICAL**: Before implementing any changes, you **MUST** follow this workflow:

### 1. Plan Phase
- **Understand the requirement**: Break down what needs to be done
- **Identify affected components**: Determine which files, modules, or systems will be modified
- **Check for specialized agents**: See if there's a subagent (Task tool) that can handle this work more effectively
- **Design the approach**: Think through the implementation strategy

### 2. Validation Strategy Phase
Before writing any code, **define how you will validate** the changes:

#### Code Validation
- Run your project's test and lint commands to validate changes
- Use formatters and linters configured for this repo and fix issues before committing

#### Helm Charts
- `helm lint charts/chart_name/` - Validate chart syntax
- `helm template charts/chart_name/ --debug` - Test template rendering
- `helm upgrade --dry-run --debug release-name charts/chart_name/` - Simulate upgrade
- `just helm-lint` - Lint all charts
- Deploy to local K8s and verify: `kubectl get pods`, `kubectl logs`, etc.

#### Terraform/Infrastructure
- `terragrunt plan` - Preview changes
- `terragrunt validate` - Validate configuration
- `terragrunt apply` - Apply changes (after plan review)

#### Docker/Containers
- `just docker-lint` - Lint Dockerfiles
- `just docker-scan` - Security scan
- `docker build` - Verify build succeeds
- Run container locally and test functionality

#### Documentation/Markdown
- Check for broken links
- Verify formatting renders correctly
- Ensure technical accuracy

#### Scripts/Justfiles
- Execute script/command to verify it works
- Test with different inputs/flags if applicable
- Check exit codes and error handling

### 3. Implementation Phase
- Implement the changes following the plan
- **Keep changes atomic and focused** - don't mix unrelated changes
- Follow all relevant guidelines from this document
- Add appropriate logging, error handling, and documentation

### 4. Verification Phase
**Execute the validation strategy** you defined in Phase 2:

- Run **all applicable validation commands**
- If any validation fails, **fix the issues immediately**
- Don't consider the task complete until all validations pass
- Document any validation results if relevant

### 5. Completion Phase
- Run `mix precommit` (Elixir projects) or equivalent quality checks
- Verify git status - ensure only intended files changed
- Use TodoWrite to mark tasks complete only when **fully validated**
- Report results to user with validation evidence

### Example Workflow

**Bad approach** (don't do this):
```
User: Add a new GraphQL mutation for creating users
Assistant: *immediately starts writing code*
Assistant: Done! I've added the mutation.
```

**Good approach** (always do this):
```
User: Add a new GraphQL mutation for creating users
Assistant: I'll add a GraphQL mutation for creating users. Let me plan this out:

**Plan:**
1. Add user creation mutation to GraphQL schema (matrix_studio)
2. Create resolver that calls matrix_core context
3. Add user creation function in matrix_core
4. Write tests for the mutation

**Validation strategy:**
- cd src && mix compile (ensure no compilation errors)
- cd src && mix test test/matrix_studio/schema/mutations/user_test.exs
- cd src && mix test test/matrix_core/accounts_test.exs
- cd src && mix credo --strict
- cd src && mix format --check-formatted

**Implementation:**
*TodoWrite to track tasks*
*Implements each component following architecture guidelines*
*Runs each validation step and fixes any issues*

**Verification:**
cd src && mix compile
# ✓ Compiled successfully

cd src && mix test test/matrix_studio/schema/mutations/user_test.exs
# ✓ All tests pass

cd src && mix credo --strict
# ✓ No issues found

cd src && mix format --check-formatted
# ✓ All files formatted

All validations passed! The mutation is complete and tested.
```

### Key Principles

1. **Never skip validation** - Every code change must be validated before completion
2. **Plan before implementing** - Know your approach and validation strategy first
3. **Use appropriate tools** - Match the validation method to the change type
4. **Fix issues immediately** - Don't accumulate technical debt
5. **Provide evidence** - Show validation results to the user
6. **Leverage specialized agents** - Use Task tool for complex workflows when available
7. **Keep it atomic** - One logical change per implementation cycle

### When to Use Specialized Agents

Consider using the Task tool with specialized subagents for:
- **matrix-helm-packager**: Helm chart updates, packaging, Kubernetes manifest changes
- **k8s-log-analyzer**: Diagnosing pod issues, analyzing logs, investigating performance
- **git-change-verifier**: Running quality checks after code changes
- **capi-cluster-manager**: CAPI infrastructure management, cluster creation/troubleshooting
- **local-cluster**: Local Kubernetes environment management
- **general-purpose**: Complex multi-step tasks, extensive code searches

These agents have access to the full validation workflow and can handle end-to-end implementation with built-in quality checks.

## Adapter Pattern for Data Access

Matrix uses the **Adapter Pattern** for all data access operations. This pattern allows switching between Ecto (production) and Mock (testing) implementations without changing business logic.

**See `src/apps/matrix_data/CLAUDE.md` for full implementation templates and code examples.**

### Key Principles

1. **Never use Repo directly in MatrixCore** - Always go through adapters
2. **Matrix.Ctx has NO adapter field** - It only contains tenant and user data
3. **Adapter selection** is configured via `Application.get_env(:matrix_data, :resource_adapter)`
4. **Mock adapters enable async tests** - No database, faster CI
5. **Business logic stays in MatrixCore** - Adapters only handle data access
6. **Always `atomize_keys`** in adapter create/update functions before passing to changesets

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
