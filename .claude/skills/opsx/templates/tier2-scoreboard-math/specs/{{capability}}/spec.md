## MODIFIED Requirements

### Requirement: {{requirement_title_1}}

{{requirement_1_body}}.

`{{helper_or_function}}` SHALL {{helper_contract}}:

1. {{contract_step_1}}.
2. {{contract_step_2}}.
3. {{contract_step_3}}.

The {{render_or_field}} SHALL be additive and backward-compatible: results JSON files predating this change ({{absent_key_clause}}) SHALL render unchanged via the existing path without raising exceptions.

#### Scenario: {{scenario_title_1a}}

- **GIVEN** {{scenario_1a_given}}
- **WHEN** {{scenario_1a_when}}
- **THEN** {{scenario_1a_then}}
- **AND** {{scenario_1a_and}}

#### Scenario: {{scenario_title_1b}}

- **GIVEN** {{scenario_1b_given}}
- **WHEN** {{scenario_1b_when}}
- **THEN** {{scenario_1b_then}}

#### Scenario: {{scenario_title_1c_backward_compat}}

- **GIVEN** {{scenario_1c_given_legacy_dict}}
- **WHEN** {{scenario_1c_when}}
- **THEN** {{scenario_1c_then_no_exception}}
- **AND** {{scenario_1c_and_default_render}}

## ADDED Requirements

### Requirement: {{requirement_title_2}}

{{requirement_2_body}} in `task2/scripts/{{primary_script}}.py`.

#### Scenario: {{scenario_title_2a}}

- **GIVEN** {{scenario_2a_given}}
- **WHEN** {{scenario_2a_when}}
- **THEN** {{scenario_2a_then}}

#### Scenario: {{scenario_title_2b}}

- **GIVEN** {{scenario_2b_given}}
- **WHEN** {{scenario_2b_when}}
- **THEN** {{scenario_2b_then}}
