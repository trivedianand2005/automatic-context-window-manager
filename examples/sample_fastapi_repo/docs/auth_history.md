# Authentication history (archived notes)

These notes are kept for historical interest only.

- 2019: the original prototype used HTTP basic authentication on every request.
- 2020: a short-lived experiment issued JWT tokens signed with a shared secret. The
  experiment was abandoned because token revocation was awkward, and all JWT code was
  removed. The authentication token format discussion is preserved in the wiki.
- 2021: the current opaque session token approach was introduced.

Token, authentication and login terminology in this document refers to those older
designs and does not describe the current code.
