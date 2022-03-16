# watson-studio-template
Blank repository template for Watson Studio, which can be used to contain one or multiple submodule repos.  

## Motivation
Watson Studio requires multiple directories to be saved to a repository, therefore the method described here can be useful for keeping these files out of a main code repository.

## Getting started

If a Watson Studio project has already been created, skip this section and move on to the `Configuring existing Watson Studio project` section

### Creating a new project from this template

1. Use this template to start a new repo that will be used to contain all the Watson Studio files.
    This repo should be hosted on the same git host as the submodule repo(s).
2. Create Watson Studio project with Git integration for the newly created **containing repo**.  The access token must be able to authenticate **both** the containing repo and the submodule repo(s)
3. Launch JupyterLab IDE and open a new terminal session and enter the following commands.
4. ```
    git config --local user.name "<your name>"
    ```
5. ```
    git config --local user.email "<your email>"
    ```
6. ```
    git submodule add <containing repo https URL>
    ```
7. ```
    git submodule update
    ```
8. Edit `credential_helper.sh` with YOUR git username

9. Run the credential helper
    ```
    ./credential_helper.sh
    ```
### Verify that git submodules work
```
cd <submodule directory>
git push 
```
Git should not prompt for username and password if configured correctly
Make sure that `GIT_USER` env variable is correctly set if any errors are thrown.

### Configuring existing Watson Studio project

1. Open project
2. Follow the Watson Studio prompts
3. Open JuypterLab IDE
4. Open a new terminal session
5. ```
    git config --local user.name "<your name>"
    ```
6. ```
    git config --local user.email "<your email>"
7. ```
    git submodule init
    ```
8. ```
    git submodule update
    ```
9. Edit `credential_helper.sh` with YOUR git username

10. Run the credential helper
    ```
    ./credential_helper.sh
    ```
11. See steps in the previous section to verify that the git submodules work.

### Subsequent use

You may have to rerun the configured `credential_helper.sh` each time you open a new jupyter session.
```
./credential_helper.sh
```
