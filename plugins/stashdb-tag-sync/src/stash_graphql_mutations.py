"""Raw GraphQL mutations for Stash API operations."""

CREATE_TAG_MUTATION = """
mutation TagCreate($input: TagCreateInput!) {
    tagCreate(input: $input) {
        id
    }
}
"""

UPDATE_TAG_MUTATION = """
mutation TagUpdate($input: TagUpdateInput!) {
    tagUpdate(input: $input) {
        id
    }
}
"""
