-- 1. PERSONA (Base para herencia de Usuario y Cliente)
CREATE TABLE Persona (
    id SERIAL PRIMARY KEY,
    Nombre VARCHAR(120) NOT NULL,
    NIT VARCHAR(30),
    telefono VARCHAR(30),
    direccion VARCHAR(200)
);

-- 2. USUARIO (Hereda de Persona)
CREATE TABLE Usuario (
    id INT PRIMARY KEY,
    login VARCHAR(60) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    rol VARCHAR(50) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_usuario_persona FOREIGN KEY (id) REFERENCES Persona(id)
);

-- 3. CLIENTE (Hereda de Persona)
CREATE TABLE Cliente (
    id INT PRIMARY KEY,
    razonSocial VARCHAR(150) NOT NULL,
    estadoAval VARCHAR(30) NOT NULL DEFAULT 'Pendiente',
    CONSTRAINT fk_cliente_persona FOREIGN KEY (id) REFERENCES Persona(id)
);

-- 4. COMPROMISO (1 Cliente -> * Compromiso)
CREATE TABLE Compromiso (
    id SERIAL PRIMARY KEY,
    cliente_id INT NOT NULL,
    codigoDocumento VARCHAR(60) NOT NULL UNIQUE,
    fechaFrima DATE NOT NULL,
    archivoPDF VARCHAR(255),
    vigente BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_compromiso_cliente FOREIGN KEY (cliente_id) REFERENCES Cliente(id)
);

-- 5. CATALOGO: MARCA, MODELO, COLOR, TIPO DE CALZADO, TALLA
CREATE TABLE Marca (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE Modelo (
    id SERIAL PRIMARY KEY,
    marca_id INT NOT NULL,
    Nombre VARCHAR(100) NOT NULL,
    CONSTRAINT fk_modelo_marca FOREIGN KEY (marca_id) REFERENCES Marca(id),
    CONSTRAINT uq_modelo_marca_nombre UNIQUE (marca_id, Nombre)
);

CREATE TABLE Color (
    id SERIAL PRIMARY KEY,
    color VARCHAR(60) NOT NULL UNIQUE
);

CREATE TABLE TipoCalzado (
    id SERIAL PRIMARY KEY,
    descripcion VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE Talla (
    id SERIAL PRIMARY KEY,
    EU VARCHAR(15),
    USA VARCHAR(15),
    JP VARCHAR(15),
    BR VARCHAR(15),
    CM VARCHAR(15)
);

-- 6. CALZADO
CREATE TABLE Calzado (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(60) NOT NULL UNIQUE,
    marca_id INT NOT NULL,
    modelo_id INT NOT NULL,
    color_id INT NOT NULL,
    tipo_calzado_id INT NOT NULL,
    talla_id INT NOT NULL,
    CONSTRAINT fk_calzado_marca FOREIGN KEY (marca_id) REFERENCES Marca(id),
    CONSTRAINT fk_calzado_modelo FOREIGN KEY (modelo_id) REFERENCES Modelo(id),
    CONSTRAINT fk_calzado_color FOREIGN KEY (color_id) REFERENCES Color(id),
    CONSTRAINT fk_calzado_tipo FOREIGN KEY (tipo_calzado_id) REFERENCES TipoCalzado(id),
    CONSTRAINT fk_calzado_talla FOREIGN KEY (talla_id) REFERENCES Talla(id)
);

-- Índice para agilizar búsquedas multicriterio de calzado
CREATE INDEX idx_calzado_busqueda
    ON Calzado (marca_id, modelo_id, color_id, talla_id);

-- 7. ALMACÉN E INVENTARIO POR ALMACÉN
CREATE TABLE Almacen (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    ubicacion VARCHAR(200) NOT NULL,
    esCentral BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE InventarioAlmacen (
    id SERIAL PRIMARY KEY,
    almacen_id INT NOT NULL,
    calzado_id INT NOT NULL,
    stockActual INT NOT NULL DEFAULT 0 CHECK (stockActual >= 0),
    CONSTRAINT fk_inventario_almacen FOREIGN KEY (almacen_id) REFERENCES Almacen(id),
    CONSTRAINT fk_inventario_calzado FOREIGN KEY (calzado_id) REFERENCES Calzado(id),
    CONSTRAINT uq_inventario_almacen_calzado UNIQUE (almacen_id, calzado_id)
);

-- 8. TRASPASOS ENTRE ALMACENES
CREATE TABLE Traspaso (
    id SERIAL PRIMARY KEY,
    numeroTraspaso VARCHAR(50) NOT NULL UNIQUE,
    fechaTraspaso TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    observacion TEXT,
    almacen_origen_id INT NOT NULL,
    almacen_destino_id INT NOT NULL,
    CONSTRAINT fk_traspaso_origen FOREIGN KEY (almacen_origen_id) REFERENCES Almacen(id),
    CONSTRAINT fk_traspaso_destino FOREIGN KEY (almacen_destino_id) REFERENCES Almacen(id),
    CONSTRAINT chk_almacenes_distintos CHECK (almacen_origen_id <> almacen_destino_id)
);

CREATE TABLE DetalleTraspaso (
    id SERIAL PRIMARY KEY,
    traspaso_id INT NOT NULL,
    calzado_id INT NOT NULL,
    Cantidad INT NOT NULL CHECK (Cantidad > 0),
    CONSTRAINT fk_detalle_traspaso FOREIGN KEY (traspaso_id) REFERENCES Traspaso(id) ON DELETE CASCADE,
    CONSTRAINT fk_detalle_traspaso_calzado FOREIGN KEY (calzado_id) REFERENCES Calzado(id)
);

-- 9. PEDIDOS Y DETALLE DE PEDIDO
CREATE TABLE Pedido (
    id SERIAL PRIMARY KEY,
    numeroPedido VARCHAR(50) NOT NULL UNIQUE,
    fechaPedido TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    estado VARCHAR(40) NOT NULL DEFAULT 'Pendiente de Análisis',
    fechaAproxEntrega DATE,
    usuario_realiza_id INT NOT NULL,
    usuario_confirma_id INT,
    CONSTRAINT fk_pedido_realiza FOREIGN KEY (usuario_realiza_id) REFERENCES Usuario(id),
    CONSTRAINT fk_pedido_confirma FOREIGN KEY (usuario_confirma_id) REFERENCES Usuario(id)
);

CREATE TABLE DetallePedido (
    id SERIAL PRIMARY KEY,
    pedido_id INT NOT NULL,
    calzado_id INT NOT NULL,
    cantidadSolicitada INT NOT NULL CHECK (cantidadSolicitada > 0),
    cantidadConfirmada INT NOT NULL DEFAULT 0 CHECK (cantidadConfirmada >= 0),
    CONSTRAINT fk_detalle_pedido FOREIGN KEY (pedido_id) REFERENCES Pedido(id) ON DELETE CASCADE,
    CONSTRAINT fk_detalle_pedido_calzado FOREIGN KEY (calzado_id) REFERENCES Calzado(id)
);