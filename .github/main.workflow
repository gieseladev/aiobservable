workflow "upload to PyPI on tag" {
  on = "push"
  resolves = [
    "upload to PyPI",
  ]
}

action "filter tag" {
  uses = "actions/bin/filter@master"
  args = "tag v*"
}

action "test" {
  uses = "jefftriplett/python-actions@master"
  args = "pytest"
  needs = "filter tag"
}

action "create distribution" {
  uses = "ross/python-actions/setup-py/3.7@master"
  args = "sdist"
  needs = "test"
}

action "upload to PyPI" {
  uses = "ross/python-actions/twine@master"
  args = "upload ./dist/aiobservable*.tar.gz"
  secrets = [
    "TWINE_USERNAME",
    "TWINE_PASSWORD",
  ]
  needs = "create distribution"
}
