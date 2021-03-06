require 'socket'
require 'json'
require 'time'


class Game
    def initialize(socket)
        @start = false
        @first_tick = false
        @socket = socket
        @timestamp = 0.0
        @prng = Random.new
    end

    def receive(data)
        # ruby with no external libs doesnt have async code
        # so I must check timestamp and run loop
        
        new_timestamp = Time.now.to_f
        if new_timestamp - @timestamp > 0.25
            tick
            @timestamp = new_timestamp
        end

        case data['status'] 
        when 'data'
            if data['action'] == 'move' then return end  # too many data ;_;
        when 'game'
            case data['action']
            when 'start' then @start = true
            when 'over' then @start = false
            end
        end

        print _get_color(data), data
        puts "\e[0m"
    end

    def tick
        if !@first_tick
            send 'action' => 'greet', 'name' => 'RUBY'
            @first_tick = true
        end

        if @start 
            action = @prng.rand(0..2)
            case action
            when 0  # random speed
                speed = @prng.rand(0..2)
                send 'action' => 'set_speed', 'speed' => speed
            when 1  # random direction
                index = @prng.rand(0..3)
                direction = ['up', 'down', 'left', 'right'][index]
                send 'action' => 'rotate', 'direction' => direction
            when 2  # SHOT SHOT
                send 'action' => 'shoot'
            end
        end
    end

    def _get_color(data)
        case data['status'] 
        when 'data'
            case data['action']
            when 'spawn' then "\e[92m"  # green color
            when 'destroy' then "\e[93m"  # orange color
            else "\e[0m"  # white color
            end
        when 'ERROR' then "\e[91m"  # red color
        when 'OK' then "\e[35m"  # purple color
        when 'game' then "\e[34m"  # blue color
        else "\e[0m"  # white color
        end
    end

    def send(data)
        @socket.puts(data.to_json)
    end
end

socket = TCPSocket.open('127.0.0.1', 8888)
game = Game.new(socket)
game.tick

while line = socket.gets
    game.receive(JSON.parse!(line))
end
socket.close
