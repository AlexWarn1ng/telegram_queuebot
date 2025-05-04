# telegram_queuebot
Description:
A Telegram bot designed to manage queues.

    Stores queue data in a JSON file.

    Can create/close queues.

    Allows reordering participants or removing them from a queue.

    Participants can join or leave the queue on their own.

Queue Creation Process:

    The admin enters a command, then specifies the queue name.

    Once created, the queue opens at a random time between A and B.

        The admin receives the exact opening time.

    Users receive notifications when the queue is created and opened.

    
    ! After the queue is closed, it remains stored in the JSON file. !
