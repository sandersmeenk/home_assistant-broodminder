# Sourced by scripts/setup, scripts/test and scripts/develop: the Home Assistant versions to work
# against. "minimum" is the oldest version the integration supports (hacs.json), "latest" the
# newest one the test plugin supports. requirements/<target>.txt pins each, and scripts/setup
# installs it in .venv-<target>.

TARGETS=(minimum latest)

# Print the targets named by $1, or all of them when $1 is empty. Exit on an unknown name.
select_targets() {
    case "$1" in
        "") echo "${TARGETS[@]}" ;;
        minimum | latest) echo "$1" ;;
        *)
            echo "Unknown Home Assistant version '$1': use minimum or latest" >&2
            exit 2
            ;;
    esac
}

# Print the Python version a target needs, from the "# python:" line of its requirements
python_version() {
    sed -n 's/^# python: //p' "requirements/$1.txt"
}

# Print the virtual environment of a target, or exit if scripts/setup hasn't created it
venv_of() {
    if [[ ! -x ".venv-$1/bin/python" ]]; then
        echo ".venv-$1 doesn't exist: run scripts/setup $1" >&2
        exit 1
    fi
    echo ".venv-$1"
}
