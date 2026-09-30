import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from prompt_to_scene.app import main

    main()
